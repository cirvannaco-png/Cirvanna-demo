from prometheus_client import Counter, Histogram, Gauge
import time

# AIS-specific metrics
segmentation_time = Histogram(
    'ais_segmentation_duration_seconds',
    'Segmentation model inference time',
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0)
)

pose_time = Histogram(
    'ais_pose_duration_seconds',
    'Pose detection model inference time',
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0)
)

smpl_fitting_time = Histogram(
    'ais_smpl_fitting_duration_seconds',
    'SMPL fitting optimization time',
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0)
)

mesh_upload_time = Histogram(
    'ais_mesh_upload_duration_seconds',
    'Mesh upload to S3 time',
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0)
)

measurement_distribution = Histogram(
    'ais_measurements_cm',
    'Distribution of body measurements',
    ['measurement'],
    buckets=(50, 60, 70, 80, 90, 100, 110, 120, 130)
)

silhouette_quality = Histogram(
    'ais_silhouette_quality',
    'Quality score of extracted silhouettes',
    buckets=(0.1, 0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 1.0)
)
