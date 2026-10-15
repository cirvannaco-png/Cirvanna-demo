import numpy as np
import logging
from src.fci.models import BodyModel, GarmentModel, BrandData, UserHistory
from src.fci.morphology import BodyMorphology, BodyShape
from src.fci.skin import SkinProfile, FitzpatrickType, Undertone, DermatologicalCondition
from src.fci.bayesian import BayesianLayer
from src.fci.neural import NeuralResidual
from src.fci.calibration import FastCalibrator
from src.fci.friction import BanditFrictionPolicy, FrictionAction
from src.fci.metrics import InMemoryMetricsCollector, PostgresMetricsCollector
from src.fci.pipeline import FitConfidenceIndex

logging.basicConfig(level=logging.INFO)

def train_bandit_example():
    """Simulate offline training of a bandit policy using historical data."""
    np.random.seed(42)
    data = []
    for _ in range(1000):
        state = {
            "fci": np.random.uniform(0, 1),
            "bmc": np.random.uniform(0, 1),
            "gsr": np.random.uniform(0, 1),
            "price": np.random.randint(0, 3),
            "brand_volatility": np.random.uniform(0, 1),
            "rigidity": np.random.uniform(0, 1),
            "user_tolerance": np.random.uniform(0, 1),
            "ci_width": np.random.uniform(0, 0.2)
        }
        action = np.random.choice(list(FrictionAction))
        if action == FrictionAction.AUTO_CONFIRM and state["fci"] > 0.8:
            reward = 1.0
        elif action == FrictionAction.SUGGEST_ALTERNATIVE and state["fci"] < 0.5:
            reward = 1.0
        else:
            reward = 0.0
        data.append((state, action, reward))

    feature_names = ["fci", "bmc", "gsr", "price", "brand_volatility", "rigidity", "user_tolerance", "ci_width"]
    bandit = BanditFrictionPolicy(feature_names, epsilon=0.1)
    bandit.train_offline(data)
    print("Bandit training completed (placeholder).")

if __name__ == "__main__":
    # Create rich body morphology
    morphology = BodyMorphology(
        height_cm=175,
        weight_kg=70,
        chest_circumference=95,
        waist_circumference=80,
        hip_circumference=98,
        shoulder_width=45,
        body_shape=BodyShape.RECTANGLE
    )

    # Create skin profile
    skin = SkinProfile(
        fitzpatrick_type=FitzpatrickType.III,
        undertone=Undertone.NEUTRAL,
        ita_angle=35.0,
        melanin_density=0.4,
        pore_density=120,
        wrinkle_depth_avg=0.2,
        hydration_level=0.7,
        sebum_production=0.3,
        elasticity_metrics=0.8,
        conditions=[DermatologicalCondition.NONE]
    )

    body = BodyModel(bmc=0.85, morphology=morphology, skin=skin)
    garment = GarmentModel(gsr=0.72, price_bucket=1, rigidity_index=0.4,
                           fabric_texture=0.3, breathability=0.8)
    brand = BrandData(bfs=0.68, brand_volatility=0.2)
    user = UserHistory(phfa=0.9, user_tolerance_index=0.7)

    # Dummy neural model (in practice, load a trained regressor)
    class DummyRegressor:
        def predict(self, X):
            return np.array([0.02] * len(X))

    # Define all possible feature names that will be passed
    feature_names = [
        "bmc", "gsr", "bfs", "phfa", "s_struct", "s_bayes",
        "price_bucket", "rigidity", "brand_volatility", "user_tolerance",
        "fabric_texture", "breathability",
        "morph_height_cm", "morph_weight_kg", "morph_bmi",
        "morph_chest_circumference", "morph_waist_circumference", "morph_hip_circumference",
        "morph_shoulder_width", "morph_body_shape",
        "skin_fitzpatrick", "skin_undertone", "skin_ita_angle",
        "skin_melanin_density", "skin_pore_density", "skin_wrinkle_depth_avg",
        "skin_hydration_level", "skin_sebum_production", "skin_elasticity_metrics",
        "skin_condition_count"
    ]
    neural = NeuralResidual(DummyRegressor(), feature_names)

    # Fast calibrator
    cal = FastCalibrator(k=20)
    dummy_scores = np.linspace(0, 1, 200)
    dummy_labels = (dummy_scores + 0.1 * np.random.randn(200) > 0.5).astype(int)
    cal.fit(dummy_scores, dummy_labels)

    # Bayesian layer with Redis (if available)
    try:
        import redis
        redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
        bayes = BayesianLayer(redis_client=redis_client)
    except:
        bayes = BayesianLayer()  # in‑memory

    # Friction policy (bandit)
    bandit = BanditFrictionPolicy(
        feature_names=["fci", "bmc", "gsr", "price", "brand_volatility", "rigidity", "user_tolerance", "ci_width"]
    )

    # Metrics collector (Postgres if available)
    try:
        import psycopg2
        from psycopg2 import pool
        pool = psycopg2.pool.SimpleConnectionPool(1, 10, user="user", password="REDACTED", host="localhost", port=5432, database="fci")
        metrics = PostgresMetricsCollector(pool)
    except:
        metrics = InMemoryMetricsCollector()

    # Instantiate FCI
    fci = FitConfidenceIndex(
        bayesian=bayes,
        neural_residual=neural,
        calibrator=cal,
        friction_policy=bandit,
        metrics_collector=metrics
    )

    # Run prediction
    result = fci.predict(
        body=body,
        garment=garment,
        brand=brand,
        user=user,
        category="dresses",
        brand_name="BrandX",
        user_id="user123",
        prediction_id="pred_001"
    )
    print("Prediction result:", result)

    # Record outcome
    fci.record_outcome("pred_001", fit_success=True, return_reason=None)

    # Compute metrics
    print("Metrics:", metrics.compute_metrics())

    # Train bandit example
    train_bandit_example()
