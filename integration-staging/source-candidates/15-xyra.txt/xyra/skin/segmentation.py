"""
Skin segmentation using U-Net or DeepLab.
"""
import cv2
import numpy as np
import torch
import torchvision.transforms as transforms
from ..config import XyraConfig

class SkinSegmenter:
    def __init__(self, config: XyraConfig):
        self.config = config
        self.device = torch.device("cuda" if config.SKIN_USE_GPU and torch.cuda.is_available() else "cpu")
        self.model = self._load_model()
        self.transform = transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize((256, 256)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])

    def _load_model(self):
        # Placeholder: load a pre-trained U-Net
        import torch.nn as nn
        class DummyUNet(nn.Module):
            def forward(self, x):
                return torch.ones(x.shape[0], 1, x.shape[2], x.shape[3])
        return DummyUNet().to(self.device)

    def segment(self, image: np.ndarray) -> np.ndarray:
        img_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        input_tensor = self.transform(img_rgb).unsqueeze(0).to(self.device)
        with torch.no_grad():
            output = self.model(input_tensor)
        mask = torch.sigmoid(output).cpu().numpy()[0, 0] > 0.5
        mask = cv2.resize(mask.astype(np.uint8), (image.shape[1], image.shape[0]), interpolation=cv2.INTER_NEAREST)
        return mask.astype(bool)
