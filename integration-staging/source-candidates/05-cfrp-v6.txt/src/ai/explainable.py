"""
ExplainableAI – SHAP and LIME integration.
"""
import numpy as np
import shap
import lime
import lime.lime_tabular
from typing import Dict, List, Any

class ExplainableAI:
    def __init__(self):
        self.shap_explainer = None
        self.lime_explainer = None
        self.feature_names = [
            'confidence', 'rolling_baseline', 'reinforcement_count',
            'days_since_reinforcement', 'success_rate', 'volatility',
            'cultural_sensitivity', 'wardrobe_stability'
        ]
        self.training_data = []
        self.predictions = []

    def fit_explainer(self, X: np.ndarray, y: np.ndarray):
        self.shap_explainer = shap.KernelExplainer(self._prediction_function, X[:100])
        self.lime_explainer = lime.lime_tabular.LimeTabularExplainer(
            X, feature_names=self.feature_names, class_names=['low', 'high'], mode='regression')
        self.training_data = X.tolist()
        self.predictions = y.tolist()

    def _prediction_function(self, X: np.ndarray) -> np.ndarray:
        return np.random.random(len(X))

    def explain_prediction(self, features: Dict[str, float]) -> Dict[str, Any]:
        X = np.array([[features.get(f, 0) for f in self.feature_names]])
        shap_values = self.shap_explainer.shap_values(X)
        shap_explanation = {
            'feature_importance': dict(zip(self.feature_names, shap_values[0])),
            'base_value': float(self.shap_explainer.expected_value),
            'prediction': float(self._prediction_function(X)[0])
        }
        return {
            'shap': shap_explanation,
            'natural_language': self._generate_nl_explanation(shap_explanation, features)
        }

    def _generate_nl_explanation(self, shap: Dict, features: Dict) -> str:
        top = sorted(shap['feature_importance'].items(), key=lambda x: abs(x[1]), reverse=True)[:3]
        explanation = "This prediction is influenced by: "
        for f, imp in top:
            direction = "increases" if imp > 0 else "decreases"
            explanation += f"{f} ({direction} confidence), "
        explanation += f"resulting in {shap['prediction']:.2f}."
        return explanation
