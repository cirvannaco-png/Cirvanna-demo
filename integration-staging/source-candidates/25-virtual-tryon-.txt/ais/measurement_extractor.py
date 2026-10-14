import numpy as np
import trimesh
from typing import Dict

class MeasurementExtractor:
    """
    Extract anthropometric measurements from a 3D mesh by slicing at anatomically defined heights.
    """
    # Anatomical slice heights as fraction of total height (from ground up)
    SLICE_HEIGHTS = {
        'ankle': 0.04,      # just above foot
        'calf': 0.15,       # mid-calf
        'knee': 0.25,       # knee center
        'thigh': 0.30,      # upper thigh
        'hip': 0.48,        # hip (widest point)
        'waist': 0.55,      # natural waist
        'chest': 0.72,      # under armpit
        'neck': 0.85,       # base of neck
        'shoulder': 0.87,   # shoulder height
    }

    def __init__(self, mesh: trimesh.Trimesh):
        self.mesh = mesh
        self.z_min, self.z_max = mesh.bounds[0][2], mesh.bounds[1][2]
        self.height = self.z_max - self.z_min

    def slice_at_height(self, z: float) -> np.ndarray:
        """Slice mesh at given z and return 2D points of intersection."""
        slice_ = self.mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
        if slice_ is None:
            return np.empty((0, 2))
        # slice_ is a Path3D, get vertices in the plane
        vertices = slice_.vertices
        return vertices[:, :2]  # drop z

    def circumference_from_points(self, points: np.ndarray) -> float:
        """Compute perimeter of convex hull of points."""
        if len(points) < 3:
            return 0.0
        from scipy.spatial import ConvexHull
        hull = ConvexHull(points)
        return hull.area  # for 2D hull, area is perimeter

    def extract_all(self) -> Dict[str, float]:
        measurements = {}
        for name, frac in self.SLICE_HEIGHTS.items():
            z = self.z_min + frac * self.height
            points = self.slice_at_height(z)
            if len(points) < 3:
                # Try small offsets
                for offset in [0.01, -0.01, 0.02, -0.02]:
                    points = self.slice_at_height(z + offset * self.height)
                    if len(points) >= 3:
                        break
            circ = self.circumference_from_points(points)
            measurements[name] = circ
        return measurements
