from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
import time
import uuid
from typing import List, Optional

from shared.garment import GarmentDescriptor
from shared.exceptions import GSISException, InvalidGarmentDataError, GarmentNotFoundError
from shared.logging import setup_logging
from shared.metrics import monitor_request, error_count

from .database import SessionLocal, engine
from .models import Base
from .service import GarmentService
from .validators import GarmentValidator
from .exceptions import DatabaseError

# Setup logging
logger = setup_logging("gsis")

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Cirvanna GSIS",
    description="Garment Structural Intelligence Service",
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

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_garment_service(db: Session = Depends(get_db)):
    return GarmentService(db)

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

@app.exception_handler(GSISException)
async def gsis_exception_handler(request: Request, exc: GSISException):
    logger.error(
        f"GSIS error: {exc.message}",
        extra={
            "trace_id": getattr(request.state, "trace_id", None),
            "error_code": exc.code,
            "details": exc.details
        }
    )
    error_count.labels(service="gsis", error_type=exc.code).inc()
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
    error_count.labels(service="gsis", error_type="unexpected").inc()
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
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint"""
    try:
        # Test database connection
        db.execute("SELECT 1").first()
        db_status = "healthy"
    except Exception as e:
        db_status = "unhealthy"
        logger.error(f"Database health check failed: {e}")

    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "service": "gsis",
        "database": db_status,
        "timestamp": time.time()
    }

@app.get("/metrics")
async def get_metrics():
    """Prometheus metrics endpoint"""
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    from starlette.responses import Response
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.post("/upload_garment")
@monitor_request("gsis")
async def upload_garment(
    gdo: GarmentDescriptor,
    request: Request,
    service: GarmentService = Depends(get_garment_service)
):
    """
    Upload and validate garment descriptor

    - **gdo**: Garment Descriptor Object
    """
    trace_id = request.state.trace_id
    logger.info(
        f"Uploading garment {gdo.garment_id}",
        extra={
            "trace_id": trace_id,
            "garment_id": gdo.garment_id
        }
    )

    try:
        # Validate with auto-correction
        warnings = GarmentValidator.validate(gdo)

        # Store
        garment = service.create_garment(gdo)

        logger.info(
            "Garment uploaded successfully",
            extra={
                "trace_id": trace_id,
                "garment_id": garment.garment_id,
                "version": garment.version
            }
        )

        response = {
            "status": "success",
            "garment_id": garment.garment_id,
            "version": garment.version,
            "message": "Garment data validated and stored"
        }
        if warnings:
            response["warnings"] = warnings
        return response

    except InvalidGarmentDataError as e:
        logger.warning(
            "Invalid garment data",
            extra={
                "trace_id": trace_id,
                "details": e.details
            }
        )
        raise
    except Exception as e:
        logger.exception(
            "Error uploading garment",
            extra={"trace_id": trace_id}
        )
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/garment/{garment_id}", response_model=GarmentDescriptor)
@monitor_request("gsis")
async def get_garment(
    garment_id: str,
    request: Request,
    service: GarmentService = Depends(get_garment_service)
):
    """
    Retrieve garment by ID (latest version)
    """
    trace_id = request.state.trace_id
    logger.info(
        f"Retrieving garment {garment_id}",
        extra={"trace_id": trace_id}
    )
    garment = service.get_garment(garment_id)
    if not garment:
        raise GarmentNotFoundError(garment_id)

    # Convert ORM to Pydantic
    return GarmentDescriptor(
        garment_id=garment.garment_id,
        size=garment.size,
        pattern_dimensions=garment.pattern_dimensions,
        stretch_ratio=garment.stretch_ratio,
        fit_class=garment.fit_class,
        fabric_weight=garment.fabric_weight,
        ease_allowance=garment.ease_allowance,
        optional_CAD_pattern=garment.cad_pattern
    )

@app.get("/garment/{garment_id}/version/{version}", response_model=GarmentDescriptor)
@monitor_request("gsis")
async def get_garment_version(
    garment_id: str,
    version: int,
    request: Request,
    service: GarmentService = Depends(get_garment_service)
):
    """
    Retrieve specific version of a garment
    """
    trace_id = request.state.trace_id
    logger.info(
        f"Retrieving garment {garment_id} version {version}",
        extra={"trace_id": trace_id}
    )
    garment = service.get_garment_version(garment_id, version)
    if not garment:
        raise GarmentNotFoundError(f"{garment_id} v{version}")

    return GarmentDescriptor(
        garment_id=garment.garment_id,
        size=garment.size,
        pattern_dimensions=garment.pattern_dimensions,
        stretch_ratio=garment.stretch_ratio,
        fit_class=garment.fit_class,
        fabric_weight=garment.fabric_weight,
        ease_allowance=garment.ease_allowance,
        optional_CAD_pattern=garment.cad_pattern
    )

@app.get("/garments")
@monitor_request("gsis")
async def list_garments(
    skip: int = 0,
    limit: int = 100,
    request: Request = None,
    service: GarmentService = Depends(get_garment_service)
):
    """
    List all garments (latest versions)
    """
    trace_id = request.state.trace_id
    logger.info(
        "Listing garments",
        extra={"trace_id": trace_id, "skip": skip, "limit": limit}
    )
    garments, total = service.list_garments(skip, limit)

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "garments": [
            {
                "garment_id": g.garment_id,
                "size": g.size,
                "version": g.version,
                "fit_class": g.fit_class,
                "fabric_weight": g.fabric_weight,
                "created_at": g.created_at.isoformat() if g.created_at else None
            }
            for g in garments
        ]
    }

@app.delete("/garment/{garment_id}")
@monitor_request("gsis")
async def delete_garment(
    garment_id: str,
    request: Request,
    service: GarmentService = Depends(get_garment_service)
):
    """
    Delete all versions of a garment
    """
    trace_id = request.state.trace_id
    logger.info(
        f"Deleting garment {garment_id}",
        extra={"trace_id": trace_id}
    )
    success = service.delete_garment(garment_id)
    if not success:
        raise GarmentNotFoundError(garment_id)

    return {"status": "deleted", "garment_id": garment_id}
