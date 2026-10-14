from fastapi import FastAPI, HTTPException, Request, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
import time
import uuid
from typing import List, Optional
import json
import tempfile
import os

from shared.body import BodyCapture, BodyMesh, CameraMetadata
from shared.exceptions import AISException, LowConfidenceError, SilhouetteError
from shared.logging import setup_logging
from shared.metrics import monitor_request, error_count

from .config import AISConfig
from .service import AIService
from .cache import BodyMeshCache
from .exceptions import AISServiceError

# Setup logging
logger = setup_logging("ais")

# Load config
config = AISConfig()

# Initialize service
ais_service = AIService(config)
cache = BodyMeshCache(config)

app = FastAPI(
    title="Cirvanna AIS",
    description="Anthropometric Intelligence Service",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_trace_id(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))
    request.state.trace_id = trace_id
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Trace-ID"] = trace_id
    response.headers["X-Process-Time"] = str(process_time)
    return response

@app.exception_handler(AISException)
async def ais_exception_handler(request: Request, exc: AISException):
    logger.error(
        f"AIS error: {exc.message}",
        extra={
            "trace_id": getattr(request.state, "trace_id", None),
            "error_code": exc.code,
            "details": exc.details
        }
    )
    error_count.labels(service="ais", error_type=exc.code).inc()
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
                "trace_id": getattr(request.state, "trace_id", None)
            }
        }
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "Unexpected error",
        extra={
            "trace_id": getattr(request.state, "trace_id", None),
            "error_type": type(exc).__name__
        }
    )
    error_count.labels(service="ais", error_type="unexpected").inc()
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "trace_id": getattr(request.state, "trace_id", None)
            }
        }
    )

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "ais",
        "timestamp": time.time(),
        "gpu_enabled": config.gpu_enabled,
        "gpu_available": ais_service.check_gpu_available()
    }

@app.get("/metrics")
async def get_metrics():
    """Prometheus metrics endpoint"""
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.post("/capture_body", response_model=BodyMesh)
@monitor_request("ais")
async def capture_body(
    request: Request,
    files: List[UploadFile] = File(..., description="2-3 images (front, side, optional back)"),
    height_cm: float = Form(..., description="Height in cm"),
    focal_length_mm: float = Form(..., description="Camera focal length in mm"),
    sensor_width_mm: float = Form(..., description="Camera sensor width in mm"),
    sensor_height_mm: float = Form(..., description="Camera sensor height in mm"),
    optional_weight_kg: Optional[float] = Form(None, description="Optional weight in kg")
):
    """
    Process body images and generate 3D mesh with measurements

    - **files**: 2-3 images (front, side, optional back)
    - **height_cm**: Height in centimeters
    - **focal_length_mm**: Camera focal length in mm
    - **sensor_width_mm**: Camera sensor width in mm
    - **sensor_height_mm**: Camera sensor height in mm
    - **optional_weight_kg**: Optional weight in kg
    """
    trace_id = request.state.trace_id
    logger.info(
        f"Processing body capture",
        extra={
            "trace_id": trace_id,
            "image_count": len(files),
            "height": height_cm
        }
    )

    # Validate file count
    if len(files) < 2 or len(files) > 3:
        raise HTTPException(
            status_code=400,
            detail="Exactly 2 or 3 images are required"
        )

    # Save uploaded files temporarily
    temp_paths = []
    try:
        for file in files:
            # Validate file type
            if not file.content_type.startswith('image/'):
                raise HTTPException(
                    status_code=400,
                    detail=f"File {file.filename} is not an image"
                )

            # Save to temp file
            suffix = os.path.splitext(file.filename)[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
                content = await file.read()
                temp.write(content)
                temp_paths.append(temp.name)

        # Create capture object
        capture = BodyCapture(
            images=temp_paths,
            height_cm=height_cm,
            camera_metadata=CameraMetadata(
                focal_length_mm=focal_length_mm,
                sensor_size_mm=[sensor_width_mm, sensor_height_mm]
            ),
            optional_weight_kg=optional_weight_kg
        )

        # Check cache
        cache_key = cache.generate_key(capture)
        cached_result = cache.get(cache_key)
        if cached_result:
            logger.info(
                "Cache hit",
                extra={"trace_id": trace_id, "cache_key": cache_key}
            )
            return cached_result

        # Process
        body_mesh = ais_service.process(capture, trace_id)

        # Cache result
        cache.set(cache_key, body_mesh)

        logger.info(
            "Body capture successful",
            extra={
                "trace_id": trace_id,
                "mesh_id": body_mesh.id,
                "confidence_tier": body_mesh.confidence_tier
            }
        )
        return body_mesh

    except LowConfidenceError as e:
        logger.warning(
            "Low confidence result",
            extra={
                "trace_id": trace_id,
                "details": e.details
            }
        )
        raise
    except SilhouetteError as e:
        logger.warning(
            "Silhouette extraction failed",
            extra={
                "trace_id": trace_id,
                "details": e.details
            }
        )
        raise
    except Exception as e:
        logger.exception(
            "Error in body capture",
            extra={"trace_id": trace_id}
        )
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Clean up temp files
        for path in temp_paths:
            try:
                os.unlink(path)
            except:
                pass

@app.get("/store_body/{mesh_id}", response_model=BodyMesh)
@monitor_request("ais")
async def get_stored_body(mesh_id: str, request: Request):
    """
    Retrieve a stored body mesh by ID
    """
    trace_id = request.state.trace_id
    logger.info(
        f"Retrieving body mesh {mesh_id}",
        extra={"trace_id": trace_id}
    )
    body_mesh = cache.get_by_id(mesh_id)
    if not body_mesh:
        raise HTTPException(status_code=404, detail="Body mesh not found")
    return body_mesh

@app.delete("/store_body/{mesh_id}")
@monitor_request("ais")
async def delete_stored_body(mesh_id: str, request: Request):
    """
    Delete a stored body mesh
    """
    trace_id = request.state.trace_id
    logger.info(
        f"Deleting body mesh {mesh_id}",
        extra={"trace_id": trace_id}
    )
    success = cache.delete_by_id(mesh_id)
    if not success:
        raise HTTPException(status_code=404, detail="Body mesh not found")
    return {"status": "deleted", "mesh_id": mesh_id}
