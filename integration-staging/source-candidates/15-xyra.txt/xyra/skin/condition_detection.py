"""
Multi-label condition detection (acne, eczema, rosacea, etc.).
"""
import cv2
import numpy as np
import torch
import torchvision.models as models
import torchvision.transforms as transforms
from ..config import XyraConfig

class ConditionDetector:
    def __init__(self, config: XyraConfig):
        self.config = config
        self.device = torch.device("cuda" if config.SKIN_USE_GPU and torch.cuda.is_available() else "cpu")
        self.model = self._load_model()
        self.transform = transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])
        self.conditions = [
            "acne_lesions", "blackheads", "whiteheads", "inflammation_redness", "rosacea_markers",
            "dehydration_level", "barrier_damage", "hyperpigmentation_spots", "post_acne_marks",
            "sun_damage_markers", "uv_damage_index", "aging_markers", "collagen_degradation",
            "eczema", "dermatitis"
        ]

    def _load_model(self):
        model = models.efficientnet_b0(pretrained=False)
        model.classifier[1] = torch.nn.Linear(1280, len(self.conditions))
        model = model.to(self.device)
        model.eval()
        return model

    def predict(self, image: np.ndarray) -> list:
        img_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        input_tensor = self.transform(img_rgb).unsqueeze(0).to(self.device)
        with torch.no_grad():
            outputs = self.model(input_tensor)
            probs = torch.sigmoid(outputs).cpu().numpy()[0]
        results = []
        for i, cond in enumerate(self.conditions):
            if probs[i] > self.config.SKIN_MIN_CONFIDENCE:
                results.append({"condition": cond, "confidence": float(probs[i])})
        return results
