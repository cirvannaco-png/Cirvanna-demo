"""
Texture analysis: pore density, roughness, elasticity, sebum, micro-line topology.
"""
import cv2
import numpy as np
from skimage import feature, filters, measure
from ..config import XyraConfig

class TextureAnalyzer:
    def __init__(self, config: XyraConfig):
        self.config = config

    def analyze(self, image: np.ndarray) -> dict:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        # Pore detection
        pores = feature.blob_log(gray, max_sigma=5, num_sigma=5, threshold=0.1)
        pore_density = len(pores) / (h * w) * 10000
        pore_diameter = np.mean([p[2] for p in pores]) if pores else 0
        pore_distribution = np.std([p[0] for p in pores]) / w if pores else 0

        # Roughness
        gabor = filters.gabor(gray, frequency=0.1)[0]
        surface_roughness_ra = np.std(gabor)
        surface_roughness_rz = np.percentile(gabor, 95) - np.percentile(gabor, 5)

        # Wrinkles and lines
        edges = cv2.Canny(gray, 50, 150)
        wrinkle_density = np.sum(edges) / (h * w)
        sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        grad_mag = np.sqrt(sobelx**2 + sobely**2)
        wrinkle_depth = np.mean(grad_mag[edges > 0]) if np.sum(edges) > 0 else 0
        fine_line_density = wrinkle_density * 0.5

        # Micro-line topology (e.g., using line detection)
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=50, minLineLength=10, maxLineGap=5)
        micro_line_topology = len(lines) / (h * w) * 10000 if lines is not None else 0

        # Elasticity proxy
        lbp = feature.local_binary_pattern(gray, P=8, R=1, method='uniform')
        lbp_var = np.var(lbp)
        elasticity = lbp_var / 100
        firmness = 1.0 - elasticity
        resilience = elasticity * 0.8

        # Microrelief pattern
        hist, _ = np.histogram(lbp, bins=np.arange(0, 11))
        hist = hist / hist.sum()
        entropy = -np.sum(hist * np.log(hist + 1e-7))
        microrelief_pattern = entropy / 3.0

        # Smoothness
        smoothness = 1.0 / (1.0 + surface_roughness_ra)

        # Sebum and oil
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        value_mean = np.mean(hsv[:,:,2])
        sebum_level = value_mean / 255.0
        oil_distribution = np.std(hsv[:,:,2]) / 255.0

        # Dryness
        sat_mean = np.mean(hsv[:,:,1]) / 255.0
        dry_patch_density = max(0, 1.0 - sat_mean * 2)
        skin_flake_density = max(0, dry_patch_density - 0.5) * 2

        return {
            "pore_density": float(pore_density),
            "pore_diameter": float(pore_diameter),
            "pore_distribution": float(pore_distribution),
            "surface_roughness_ra": float(surface_roughness_ra),
            "surface_roughness_rz": float(surface_roughness_rz),
            "wrinkle_count": float(wrinkle_density * 1000),
            "wrinkle_depth": float(wrinkle_depth),
            "fine_line_density": float(fine_line_density * 1000),
            "micro_line_topology": float(micro_line_topology),
            "elasticity": float(elasticity),
            "firmness": float(firmness),
            "resilience": float(resilience),
            "microrelief_pattern": float(microrelief_pattern),
            "smoothness": float(smoothness),
            "sebum_level": float(sebum_level),
            "oil_distribution": float(oil_distribution),
            "dry_patch_density": float(dry_patch_density),
            "skin_flake_density": float(skin_flake_density),
            "confidence": 0.7
        }
