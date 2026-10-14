"""
Vectorized ingredient analysis.
"""
import numpy as np
from enum import Enum, auto

class SkinType(Enum):
    DRY = auto()
    OILY = auto()
    COMBINATION = auto()
    NORMAL = auto()
    SENSITIVE = auto()

class IngredientAnalyzer:
    def __init__(self):
        self.ingredient_vectors = self._load_ingredient_vectors()
        self.ingredient_index = {ing: idx for idx, ing in enumerate(self.ingredient_vectors.keys())}
        self.compatibility_matrix = np.array([
            [0.9, 0.1, 0.3, 0.7, 0.2],
            [0.1, 0.9, 0.5, 0.3, 0.2],
            [0.8, 0.2, 0.6, 0.5, 0.9],
            [0.1, 0.8, 0.4, 0.2, 0.1],
            [0.2, 0.1, 0.2, 0.1, 0.0],
        ])

    def _load_ingredient_vectors(self):
        return {
            "hyaluronic_acid": [1, 0, 0, 0, 0],
            "salicylic_acid": [0, 1, 0, 0, 0],
            "ceramides": [0, 0, 1, 0, 0],
            "niacinamide": [0, 0, 0, 1, 0],
            "fragrance": [0, 0, 0, 0, 1],
        }

    def analyze_batch(self, skin_types, ingredient_lists):
        n_skin_types = len(skin_types)
        n_products = len(ingredient_lists)
        ingredient_matrix = np.zeros((n_products, len(self.ingredient_vectors)))
        for i, ingredients in enumerate(ingredient_lists):
            for ing in ingredients:
                if ing in self.ingredient_index:
                    ingredient_matrix[i, self.ingredient_index[ing]] = 1
        skin_type_indices = np.array([st.value - 1 for st in skin_types])
        compatibility = np.zeros((n_skin_types, n_products))
        for i, st_idx in enumerate(skin_type_indices):
            compat_vector = self.compatibility_matrix[:, st_idx]
            compatibility[i, :] = ingredient_matrix @ compat_vector
        compatibility = np.clip(compatibility / 5.0, 0.0, 1.0)
        return compatibility
