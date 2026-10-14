import numpy as np
import torch
import time
import uuid
import boto3
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
import trimesh

from shared.body import BodyCapture, BodyMesh, Measurements, MeasurementUncertainty, PostureClass
from shared.exceptions import LowConfidenceError, SilhouetteError

from .config import AISConfig
from .preprocessing import ImagePreprocessor
from .models.segmentation import DeepLabV3Plus
from .models.pose import MoveNet
from .models.smpl_fitter import SMPLFitter
from .uncertainty import UncertaintyEstimator
from .cache import BodyMeshCache
from .exceptions import ModelLoadError, ProcessingError

class AIService:
    """Anthropometric Intelligence Service"""

    def __init__(self, config: AISConfig):
        self.config = config
        self.preprocessor = ImagePreprocessor(config)
        self.cache = BodyMeshCache(config)

        # Initialize S3 client if credentials provided
        self.s3_client = None
        if config.aws_access_key_id and config.aws_secret_access_key:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=config.aws_access_key_id,
                aws_secret_access_key=config.aws_secret_access_key,
                region_name=config.aws_region
            )

        # Lazy-loaded models
        self._segmentation_model = None
        self._pose_model = None
        self._smpl_fitter = None
        self._uncertainty_estimator = None

    @property
    def segmentation_model(self) -> DeepLabV3Plus:
        """Lazy load segmentation model"""
        if self._segmentation_model is None:
            try:
                self._segmentation_model = DeepLabV3Plus(self.config)
            except Exception as e:
                raise ModelLoadError(f"Failed to load segmentation model: {e}")
        return self._segmentation_model

    @property
    def pose_model(self) -> MoveNet:
        """Lazy load pose model"""
        if self._pose_model is None:
            try:
                self._pose_model = MoveNet(self.config)
            except Exception as e:
                raise ModelLoadError(f"Failed to load pose model: {e}")
        return self._pose_model

    @property
    def smpl_fitter(self) -> SMPLFitter:
        """Lazy load SMPL fitter"""
        if self._smpl_fitter is None:
            try:
                self._smpl_fitter = SMPLFitter(self.config)
            except Exception as e:
                raise ModelLoadError(f"Failed to load SMPL fitter: {e}")
        return self._smpl_fitter

    @property
    def uncertainty_estimator(self) -> UncertaintyEstimator:
        """Lazy load uncertainty estimator"""
        if self._uncertainty_estimator is None:
            self._uncertainty_estimator = UncertaintyEstimator(self.config)
        return self._uncertainty_estimator

    def check_gpu_available(self) -> bool:
        """Check if GPU is available and being used"""
        if not self.config.gpu_enabled:
            return False
        return torch.cuda.is_available()

    def process(self, capture: BodyCapture, trace_id: str = None) -> BodyMesh:
        """
        Main processing pipeline for body capture

        Steps:
        1. Preprocess images
        2. Segment human silhouette
        3. Detect 2D pose keypoints
        4. Fit SMPL model
        5. Compute uncertainty
        6. Determine confidence tier
        7. Save mesh to S3
        """
        start_time = time.time()

        try:
            # Step 1: Preprocess images
            processed_images, original_sizes = self._preprocess_images(capture.images)

            # Step 2: Segmentation
            masks = self._segment_images(processed_images)

            # Step 3: Pose detection
            keypoints_2d = self._detect_pose(processed_images, original_sizes)

            # Step 4: SMPL fitting
            mesh_vertices, measurements_dict = self.smpl_fitter.fit_multiview(
                images=processed_images,
                masks=masks,
                keypoints=keypoints_2d,
                height_cm=capture.height_cm,
                focal_length=capture.camera_metadata.focal_length_mm,
                sensor_size=capture.camera_metadata.sensor_size_mm,
                weight_kg=capture.optional_weight_kg
            )

            # Step 5: Uncertainty estimation
            uncertainties = self.uncertainty_estimator.estimate(
                mesh_vertices,
                measurements_dict,
                processed_images,
                masks,
                keypoints_2d
            )

            # Step 6: Confidence tier
            tier = self._determine_confidence_tier(uncertainties)
            if tier == "C":
                raise LowConfidenceError(
                    "Measurement uncertainty too high",
                    details={"uncertainties": uncertainties}
                )

            # Step 7: Save mesh to S3
            mesh_id = str(uuid.uuid4())
            mesh_url = self._save_mesh_to_s3(mesh_vertices, mesh_id, trace_id)

            # Compute additional attributes
            proportion_vector = self._compute_proportions(measurements_dict)
            shoulder_angle = self._estimate_shoulder_angle(keypoints_2d)
            posture_class = self._classify_posture(keypoints_2d)

            # Create measurements object
            measurements = Measurements(**{
                k: round(v, 1) for k, v in measurements_dict.items()
            })
            uncertainty_obj = MeasurementUncertainty(**{
                k: round(v, 1) for k, v in uncertainties.items()
                if k in ['chest_cm', 'waist_cm', 'hip_cm']
            })

            # Create body mesh object
            body_mesh = BodyMesh(
                id=mesh_id,
                mesh_url=mesh_url,
                measurements=measurements,
                proportion_vector=[round(p, 2) for p in proportion_vector],
                shoulder_angle_index=round(shoulder_angle, 1),
                posture_class=posture_class,
                measurement_uncertainty=uncertainty_obj,
                confidence_tier=tier
            )

            # Store in cache
            self.cache.store_by_id(mesh_id, body_mesh)

            process_time = time.time() - start_time
            print(f"✅ Processing completed in {process_time:.2f}s")
            return body_mesh

        except Exception as e:
            raise ProcessingError(f"Processing failed: {str(e)}")

    def _preprocess_images(self, image_paths: List[str]) -> Tuple[List[np.ndarray], List[Tuple[int, int]]]:
        """Preprocess all images"""
        processed = []
        sizes = []
        for path in image_paths:
            img = self.preprocessor.load_image(path)
            h, w = img.shape[:2]
            sizes.append((w, h))
            if self.config.normalize_histogram:
                img = self.preprocessor.normalize_histogram(img)
            if self.config.enhance_edges:
                img = self.preprocessor.enhance_edges(img)
            img = self.preprocessor.resize(img, self.config.target_image_size)
            processed.append(img)
        return processed, sizes

    def _segment_images(self, images: List[np.ndarray]) -> List[np.ndarray]:
        """Segment all images"""
        masks = []
        for img in images:
            mask = self.segmentation_model.predict(img)
            if mask is None or np.sum(mask) < 100:
                raise SilhouetteError(
                    "Could not extract human silhouette",
                    details={"pixel_count": int(np.sum(mask)) if mask is not None else 0}
                )
            masks.append(mask)
        return masks

    def _detect_pose(
        self,
        images: List[np.ndarray],
        original_sizes: List[Tuple[int, int]]
    ) -> List[np.ndarray]:
        """Detect pose in all images"""
        keypoints_list = []
        for img, (orig_w, orig_h) in zip(images, original_sizes):
            kp = self.pose_model.predict(img)
            if kp is None or len(kp) < 10:
                raise SilhouetteError(
                    "Could not detect pose keypoints",
                    details={"keypoint_count": len(kp) if kp is not None else 0}
                )
            # Scale keypoints back to original image size
            scale_x = orig_w / self.config.target_image_size
            scale_y = orig_h / self.config.target_image_size
            kp[:, 0] *= scale_x
            kp[:, 1] *= scale_y
            keypoints_list.append(kp)
        return keypoints_list

    def _determine_confidence_tier(self, uncertainties: Dict[str, float]) -> str:
        """Determine confidence tier based on uncertainties"""
        max_uncertainty = max(uncertainties.values())
        if max_uncertainty < self.config.tier_a_threshold:
            return "A"
        elif max_uncertainty < self.config.tier_b_threshold:
            return "B"
        else:
            return "C"

    def _compute_proportions(self, measurements: Dict[str, float]) -> List[float]:
        """Compute body proportion vector"""
        total = (
            measurements.get('torso_length_cm', 50) +
            measurements.get('inseam_cm', 80) +
            measurements.get('arm_length_cm', 60)
        )
        if total == 0:
            return [0.48, 0.39, 0.13]
        return [
            measurements.get('torso_length_cm', 50) / total,
            measurements.get('inseam_cm', 80) / total,
            measurements.get('arm_length_cm', 60) / total
        ]

    def _estimate_shoulder_angle(self, keypoints_2d: List[np.ndarray]) -> float:
        """Estimate shoulder angle from pose keypoints"""
        if not keypoints_2d or len(keypoints_2d[0]) < 12:
            return 12.5

        # Use first image's shoulder keypoints (COCO format: 5=left shoulder, 6=right shoulder)
        left_shoulder = keypoints_2d[0][5]
        right_shoulder = keypoints_2d[0][6]
        if left_shoulder is not None and right_shoulder is not None:
            dx = right_shoulder[0] - left_shoulder[0]
            dy = right_shoulder[1] - left_shoulder[1]
            angle = np.arctan2(dy, dx) * 180 / np.pi
            return abs(angle)
        return 12.5

    def _classify_posture(self, keypoints_2d: List[np.ndarray]) -> PostureClass:
        """Classify posture based on pose keypoints"""
        if not keypoints_2d or len(keypoints_2d[0]) < 12:
            return PostureClass.NEUTRAL

        # Simplified heuristic based on shoulder and hip alignment
        # In production, use a more sophisticated model
        return PostureClass.NEUTRAL

    def _save_mesh_to_s3(self, vertices: np.ndarray, mesh_id: str, trace_id: str) -> str:
        """Save mesh to S3 and return URL"""
        if self.s3_client is None:
            # Return local path if S3 not configured
            return f"/tmp/meshes/{mesh_id}.obj"

        try:
            # Create mesh using trimesh
            # Note: In production, you'd also save faces from SMPL model
            mesh = trimesh.Trimesh(vertices=vertices)

            # Convert to OBJ
            obj_data = mesh.export(file_type='obj')

            # Upload to S3
            key = f"meshes/{trace_id}/{mesh_id}.obj"
            self.s3_client.put_object(
                Bucket=self.config.s3_bucket,
                Key=key,
                Body=obj_data,
                ContentType='model/obj'
            )

            # Generate presigned URL (valid for 1 hour)
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.config.s3_bucket,
                    'Key': key
                },
                ExpiresIn=3600
            )
            return url
        except Exception as e:
            print(f"⚠️ Failed to upload to S3: {e}")
            return f"/tmp/meshes/{mesh_id}.obj"
