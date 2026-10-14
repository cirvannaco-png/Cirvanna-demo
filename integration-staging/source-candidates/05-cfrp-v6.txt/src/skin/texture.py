"""
Skin texture: pore density, wrinkle depth, roughness.
"""
import numpy as np
from scipy import ndimage

class TextureAnalyzer:
    @staticmethod
    def pore_density(gray_image: np.ndarray, threshold: float = 0.7) -> float:
        edges = ndimage.sobel(gray_image)
        pores = (edges > threshold * edges.max()).sum()
        return pores / (gray_image.shape[0] * gray_image.shape[1])

    @staticmethod
    def wrinkle_depth(gray_image: np.ndarray) -> float:
        local_std = ndimage.generic_filter(gray_image, np.std, size=5)
        return float(np.mean(local_std))

    @staticmethod
    def surface_roughness(gray_image: np.ndarray) -> float:
        return float(np.mean(np.abs(gray_image - np.mean(gray_image))))
