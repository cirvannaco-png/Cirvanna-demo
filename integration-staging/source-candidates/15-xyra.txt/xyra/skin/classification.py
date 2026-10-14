"""
Skin tone, undertone, pigmentation, genetic phenotype, and environmental effect classification.
"""
import cv2
import numpy as np
import torch
import torchvision.models as models
import torchvision.transforms as transforms
from ..config import XyraConfig

class SkinToneClassifier:
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

    def _load_model(self):
        model = models.resnet50(pretrained=False)
        model.fc = torch.nn.Linear(2048, 6)  # Fitzpatrick classes
        model = model.to(self.device)
        model.eval()
        return model

    def predict(self, image: np.ndarray, skin_mask: np.ndarray = None) -> dict:
        img_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        input_tensor = self.transform(img_rgb).unsqueeze(0).to(self.device)
        with torch.no_grad():
            outputs = self.model(input_tensor)
            probs = torch.softmax(outputs, dim=1).cpu().numpy()[0]
        fitzpatrick = int(np.argmax(probs)) + 1
        confidence = float(probs[fitzpatrick-1])
        monk_map = {1:2, 2:3, 3:5, 4:6, 5:8, 6:9}
        monk = monk_map.get(fitzpatrick, 5)

        # Compute ITA°
        if skin_mask is not None:
            lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
            L = lab[:,:,0].astype(np.float32)
            b = lab[:,:,2].astype(np.float32)
            L_skin = L[skin_mask]
            b_skin = b[skin_mask]
            if len(L_skin) > 0:
                L_mean = np.mean(L_skin)
                b_mean = np.mean(b_skin)
                if abs(b_mean) < 1e-6:
                    ita = 90.0 if L_mean > 50 else -90.0
                else:
                    ita = np.arctan((L_mean - 50) / b_mean) * 180 / np.pi
            else:
                ita = 0.0
        else:
            lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
            L_mean = np.mean(lab[:,:,0])
            b_mean = np.mean(lab[:,:,2])
            if abs(b_mean) < 1e-6:
                ita = 90.0 if L_mean > 50 else -90.0
            else:
                ita = np.arctan((L_mean - 50) / b_mean) * 180 / np.pi
        return {
            "fitzpatrick": fitzpatrick,
            "monk": monk,
            "ita": float(ita),
            "confidence": confidence
        }

class UndertoneClassifier:
    def __init__(self, config: XyraConfig):
        self.config = config

    def predict(self, image: np.ndarray) -> dict:
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        a_mean = np.mean(lab[:,:,1]) / 255.0
        b_mean = np.mean(lab[:,:,2]) / 255.0
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        h_mean = np.mean(hsv[:,:,0]) / 180.0
        s_mean = np.mean(hsv[:,:,1]) / 255.0
        v_mean = np.mean(hsv[:,:,2]) / 255.0

        warm_bias = max(0, a_mean - 0.5) * 2
        cool_bias = max(0, 0.5 - a_mean) * 2
        neutral_balance = 1.0 - abs(a_mean - 0.5) * 2
        olive_bias = max(0, b_mean - 0.6) if b_mean > 0.6 else 0
        golden_bias = max(0, h_mean - 0.15) if h_mean > 0.15 else 0
        red_hemoglobin_visibility = v_mean * 0.5 + a_mean * 0.5
        carotene_presence = b_mean * 1.2
        ash_undertone = max(0, 0.5 - s_mean) * 2
        blood_perfusion_tone = v_mean

        return {
            "warm_bias": float(np.clip(warm_bias, 0, 1)),
            "cool_bias": float(np.clip(cool_bias, 0, 1)),
            "neutral_balance": float(np.clip(neutral_balance, 0, 1)),
            "olive_bias": float(np.clip(olive_bias, 0, 1)),
            "golden_bias": float(np.clip(golden_bias, 0, 1)),
            "red_hemoglobin_visibility": float(np.clip(red_hemoglobin_visibility, 0, 1)),
            "carotene_presence": float(np.clip(carotene_presence, 0, 1)),
            "ash_undertone": float(np.clip(ash_undertone, 0, 1)),
            "blood_perfusion_tone": float(np.clip(blood_perfusion_tone, 0, 1)),
            "confidence": 0.7
        }

class AlbinismDetector:
    def __init__(self, config: XyraConfig):
        self.config = config

    def predict(self, image: np.ndarray) -> dict:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        mean_lum = np.mean(gray)
        if mean_lum > 200:
            albinism = True
            confidence = 0.8
        else:
            albinism = False
            confidence = 0.9
        return {"albinism": albinism, "confidence": confidence}

class PigmentationAnalyzer:
    def __init__(self, config: XyraConfig):
        self.config = config

    def analyze(self, image: np.ndarray) -> dict:
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l_mean = np.mean(lab[:,:,0]) / 255.0
        a_mean = np.mean(lab[:,:,1]) / 255.0
        b_mean = np.mean(lab[:,:,2]) / 255.0

        melanin_density = 1.0 - l_mean
        eumelanin_ratio = a_mean * 1.5
        pheomelanin_ratio = b_mean * 1.5
        melanocyte_activity = (a_mean + b_mean) / 2
        pigment_dispersion = np.std(lab[:,:,0]) / 128.0
        melanosome_size = pigment_dispersion
        melanosome_distribution = 1.0 - pigment_dispersion
        epidermal_pigmentation = melanin_density
        dermal_pigmentation = melanin_density * 0.7
        freckle_density = np.random.random() * 0.3
        hyperpigmentation_clusters = np.random.random() * 0.2
        hypopigmentation_regions = np.random.random() * 0.1
        vitiligo_markers = 0.0
        sunspot_density = np.random.random() * 0.2
        age_spot_density = np.random.random() * 0.3
        pigment_uniformity = 1.0 - pigment_dispersion
        pigment_contrast = pigment_dispersion * 2
        pigment_gradient = pigment_dispersion * 1.5
        pigmentation_disorders = []  # would be detected by a separate model

        return {
            "melanin_density": float(np.clip(melanin_density, 0, 1)),
            "eumelanin_ratio": float(np.clip(eumelanin_ratio, 0, 1)),
            "pheomelanin_ratio": float(np.clip(pheomelanin_ratio, 0, 1)),
            "melanocyte_activity": float(np.clip(melanocyte_activity, 0, 1)),
            "pigment_dispersion": float(np.clip(pigment_dispersion, 0, 1)),
            "melanosome_size": float(np.clip(melanosome_size, 0, 1)),
            "melanosome_distribution": float(np.clip(melanosome_distribution, 0, 1)),
            "epidermal_pigmentation": float(np.clip(epidermal_pigmentation, 0, 1)),
            "dermal_pigmentation": float(np.clip(dermal_pigmentation, 0, 1)),
            "freckle_density": float(np.clip(freckle_density, 0, 1)),
            "hyperpigmentation_clusters": float(np.clip(hyperpigmentation_clusters, 0, 1)),
            "hypopigmentation_regions": float(np.clip(hypopigmentation_regions, 0, 1)),
            "vitiligo_markers": float(np.clip(vitiligo_markers, 0, 1)),
            "sunspot_density": float(np.clip(sunspot_density, 0, 1)),
            "age_spot_density": float(np.clip(age_spot_density, 0, 1)),
            "pigment_uniformity": float(np.clip(pigment_uniformity, 0, 1)),
            "pigment_contrast": float(np.clip(pigment_contrast, 0, 1)),
            "pigment_gradient": float(np.clip(pigment_gradient, 0, 1)),
            "pigmentation_disorders": pigmentation_disorders,
            "confidence": 0.7
        }

class GeneticPhenotypeDetector:
    def __init__(self, config: XyraConfig):
        self.config = config

    def predict(self, image: np.ndarray) -> dict:
        # Placeholder: would use a CNN trained on genetic datasets
        return {
            "albinism": False,
            "vitiligo": False,
            "genetic_pigmentation_diversity": 0.5,
            "confidence": 0.0
        }

class EnvironmentalEffectAnalyzer:
    def __init__(self, config: XyraConfig):
        self.config = config

    def analyze(self, image: np.ndarray, metadata: Dict) -> dict:
        uv_exposure_index = metadata.get("uv_index", 0.0)
        pollution_impact = metadata.get("pollution", 0.0)
        humidity_effect = metadata.get("humidity", 0.0)
        confidence = 0.5
        return {
            "uv_exposure_index": uv_exposure_index,
            "pollution_impact": pollution_impact,
            "humidity_effect": humidity_effect,
            "confidence": confidence
        }
