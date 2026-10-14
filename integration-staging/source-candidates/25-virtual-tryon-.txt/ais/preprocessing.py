import cv2
import numpy as np
from typing import Tuple, Optional

from .config import AISConfig

class ImagePreprocessor:
    """Image preprocessing utilities"""

    def __init__(self, config: AISConfig):
        self.config = config
        self.target_size = config.target_image_size

    def load_image(self, image_path: str) -> np.ndarray:
        """
        Load image from path

        Args:
            image_path: Path to image file

        Returns:
            RGB image as numpy array
        """
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Could not load image: {image_path}")

        # Convert BGR to RGB
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    def normalize_histogram(self, image: np.ndarray) -> np.ndarray:
        """
        Apply histogram equalization to improve contrast

        Args:
            image: RGB image

        Returns:
            Histogram-equalized RGB image
        """
        if not self.config.normalize_histogram:
            return image

        # Convert to YUV color space
        yuv = cv2.cvtColor(image, cv2.COLOR_RGB2YUV)

        # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        yuv[:, :, 0] = clahe.apply(yuv[:, :, 0])

        # Convert back to RGB
        return cv2.cvtColor(yuv, cv2.COLOR_YUV2RGB)

    def enhance_edges(self, image: np.ndarray) -> np.ndarray:
        """
        Enhance edges using unsharp masking

        Args:
            image: RGB image

        Returns:
            Edge-enhanced RGB image
        """
        if not self.config.enhance_edges:
            return image

        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)

        # Apply unsharp masking
        blurred = cv2.GaussianBlur(gray, (0, 0), 3.0)
        enhanced = cv2.addWeighted(gray, 1.5, blurred, -0.5, 0)

        # Convert back to 3-channel
        enhanced_rgb = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2RGB)

        return enhanced_rgb

    def resize(self, image: np.ndarray, target_size: int) -> np.ndarray:
        """
        Resize image to target size while maintaining aspect ratio,
        padding to square if necessary

        Args:
            image: Input image
            target_size: Desired output size (width and height)

        Returns:
            Resized and padded square image
        """
        h, w = image.shape[:2]

        # Determine scaling factor
        scale = target_size / max(h, w)
        new_h, new_w = int(h * scale), int(w * scale)

        # Resize
        resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

        # Pad to square
        pad_h = max(0, target_size - new_h)
        pad_w = max(0, target_size - new_w)
        pad_top = pad_h // 2
        pad_bottom = pad_h - pad_top
        pad_left = pad_w // 2
        pad_right = pad_w - pad_left

        padded = cv2.copyMakeBorder(
            resized,
            pad_top, pad_bottom, pad_left, pad_right,
            cv2.BORDER_CONSTANT,
            value=[0, 0, 0]
        )

        return padded

    def resize_to_original(self, image: np.ndarray, target_size: Tuple[int, int]) -> np.ndarray:
        """
        Resize image back to original dimensions

        Args:
            image: Processed image
            target_size: (width, height) of original image

        Returns:
            Resized image
        """
        return cv2.resize(image, target_size, interpolation=cv2.INTER_LINEAR)

    def augment_training(
        self,
        image: np.ndarray,
        mask: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Data augmentation for training

        Args:
            image: Input image
            mask: Segmentation mask

        Returns:
            Augmented image and mask
        """
        # Random horizontal flip
        if np.random.random() > 0.5:
            image = cv2.flip(image, 1)
            mask = cv2.flip(mask, 1)

        # Random rotation
        angle = np.random.uniform(-10, 10)
        h, w = image.shape[:2]
        M = cv2.getRotationMatrix2D((w/2, h/2), angle, 1)
        image = cv2.warpAffine(image, M, (w, h), borderMode=cv2.BORDER_CONSTANT)
        mask = cv2.warpAffine(mask, M, (w, h), borderMode=cv2.BORDER_CONSTANT)

        # Random brightness/contrast
        alpha = np.random.uniform(0.8, 1.2)
        beta = np.random.uniform(-20, 20)
        image = cv2.convertScaleAbs(image, alpha=alpha, beta=beta)

        return image, mask
