"""
Skin tone classification using Fitzpatrick, Monk, CIELAB.
"""
from enum import IntEnum
import numpy as np

class FitzpatrickType(IntEnum):
    I = 1
    II = 2
    III = 3
    IV = 4
    V = 5
    VI = 6

class MonkSkinTone(IntEnum):
    TONE_1 = 1
    TONE_2 = 2
    TONE_3 = 3
    TONE_4 = 4
    TONE_5 = 5
    TONE_6 = 6
    TONE_7 = 7
    TONE_8 = 8
    TONE_9 = 9
    TONE_10 = 10

class SkinToneAnalyzer:
    @staticmethod
    def estimate_fitzpatrick_from_lab(lab_image: np.ndarray) -> FitzpatrickType:
        L_mean = np.mean(lab_image[..., 0])
        if L_mean > 80:
            return FitzpatrickType.I
        elif L_mean > 70:
            return FitzpatrickType.II
        elif L_mean > 60:
            return FitzpatrickType.III
        elif L_mean > 50:
            return FitzpatrickType.IV
        elif L_mean > 40:
            return FitzpatrickType.V
        else:
            return FitzpatrickType.VI

    @staticmethod
    def estimate_monk_from_rgb(rgb_image: np.ndarray) -> MonkSkinTone:
        gray = np.dot(rgb_image[...,:3], [0.299, 0.587, 0.114])
        mean_lum = np.mean(gray)
        idx = int(np.clip(mean_lum / 255 * 10, 0, 9))
        return MonkSkinTone(idx + 1)
