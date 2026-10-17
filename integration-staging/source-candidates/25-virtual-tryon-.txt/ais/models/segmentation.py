import torch
import torch.nn as nn
import torchvision.transforms as transforms
import numpy as np
from typing import Optional
from PIL import Image
import os
import requests
from tqdm import tqdm

class DeepLabV3Plus:
    """DeepLabV3+ segmentation model wrapper"""

    def __init__(self, config):
        self.config = config
        self.device = torch.device(
            f"cuda:{config.gpu_device}" if config.gpu_enabled and torch.cuda.is_available() else "cpu"
        )

        # Load model
        self.model = torch.hub.load(
            'pytorch/vision',
            'deeplabv3_resnet50',
            pretrained=True,
            weights='DeepLabV3_ResNet50_Weights.COCO_WITH_VOC_LABELS_V1'
        )
        self.model = self.model.to(self.device)
        self.model.eval()

        # Preprocessing
        self.transform = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225]
            )
        ])

    @staticmethod
    def download_weights(path: str):
        """Download pretrained weights if not present"""
        os.makedirs(path, exist_ok=True)
        # PyTorch hub will handle download automatically
        print(f"✅ DeepLabV3+ weights will be downloaded on first use")

    def predict(self, image: np.ndarray) -> np.ndarray:
        """
        Predict human silhouette mask

        Args:
            image: RGB image as numpy array (H, W, 3)

        Returns:
            Binary mask (H, W) where 1 = human, 0 = background
        """
        # Convert to PIL Image
        if isinstance(image, np.ndarray):
            image = Image.fromarray(image)

        # Preprocess
        input_tensor = self.transform(image).unsqueeze(0).to(self.device)

        # Inference
        with torch.no_grad():
            output = self.model(input_tensor)['out'][0]

        # Get class with highest probability
        output = output.argmax(0).cpu().numpy()

        # Class 15 is "person" in COCO
        person_mask = (output == 15).astype(np.uint8)

        # Post-process: morphological operations
        import cv2
        kernel = np.ones((5, 5), np.uint8)
        person_mask = cv2.morphologyEx(person_mask, cv2.MORPH_CLOSE, kernel)
        person_mask = cv2.morphologyEx(person_mask, cv2.MORPH_OPEN, kernel)
        # Fill holes
        person_mask = cv2.morphologyEx(person_mask, cv2.MORPH_CLOSE, kernel)

        return person_mask

    def predict_batch(self, images: List[np.ndarray]) -> List[np.ndarray]:
        """
        Predict on batch of images

        Args:
            images: List of RGB images

        Returns:
            List of binary masks
        """
        batch = []
        for img in images:
            if isinstance(img, np.ndarray):
                img = Image.fromarray(img)
            batch.append(self.transform(img))

        batch_tensor = torch.stack(batch).to(self.device)

        with torch.no_grad():
            outputs = self.model(batch_tensor)['out']

        masks = []
        for output in outputs:
            mask = output.argmax(0).cpu().numpy()
            person_mask = (mask == 15).astype(np.uint8)
            # Post-process
            import cv2
            kernel = np.ones((5, 5), np.uint8)
            person_mask = cv2.morphologyEx(person_mask, cv2.MORPH_CLOSE, kernel)
            person_mask = cv2.morphologyEx(person_mask, cv2.MORPH_OPEN, kernel)
            masks.append(person_mask)

        return masks
