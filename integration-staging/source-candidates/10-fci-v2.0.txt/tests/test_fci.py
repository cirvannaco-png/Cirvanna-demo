import pytest
import numpy as np
from unittest.mock import MagicMock, patch
from src.fci.models import BodyModel, GarmentModel, BrandData, UserHistory
from src.fci.morphology import BodyMorphology, BodyShape
from src.fci.skin import SkinProfile, FitzpatrickType, Undertone, DermatologicalCondition
from src.fci.bayesian import BayesianLayer
from src.fci.neural import NeuralResidual
from src.fci.calibration import FastCalibrator
from src.fci.friction import FrictionAction, RuleBasedFrictionPolicy, BanditFrictionPolicy
from src.fci.metrics import InMemoryMetricsCollector, PostgresMetricsCollector
from src.fci.pipeline import FitConfidenceIndex

class TestInputValidation:
    def test_body_model(self):
        with pytest.raises(ValueError):
            BodyModel(bmc=1.5)
        BodyModel(bmc=0.5)  # should pass

    def test_garment_model(self):
        with pytest.raises(ValueError):
            GarmentModel(gsr=-0.1, price_bucket=0, rigidity_index=0.5)

    # similarly for others

class TestMorphology:
    def test_bmi_auto_compute(self):
        morph = BodyMorphology(height_cm=170, weight_kg=70)
        assert morph.bmi == pytest.approx(70 / (1.7**2))

class TestSkin:
    def test_skin_conditions_default(self):
        skin = SkinProfile(fitzpatrick_type=FitzpatrickType.III, undertone=Undertone.NEUTRAL)
        assert skin.conditions == []

class TestBayesianLayer:
    def test_in_memory_update_and_predict(self):
        bayes = BayesianLayer()  # no redis
        bayes.update("dress", "brandA", "user1", successes=3, trials=5)
        bayes.update("dress", "brandA", "user1", successes=2, trials=3)
        pred = bayes.predict("dress", "brandA", "user1")
        assert pred == 5/8  # 0.625

    def test_redis_mocked(self):
        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {}
        bayes = BayesianLayer(redis_client=mock_redis)
        bayes.update("dress", "brandA", "user1", successes=3, trials=5)
        mock_redis.hset.assert_called()
        mock_redis.hgetall.return_value = {b'alpha': 3.0, b'beta': 2.0}
        pred = bayes.predict("dress", "brandA", "user1")
        assert pred == 3/5  # 0.6

class TestFastCalibrator:
    def test_fit_and_predict(self):
        X = np.linspace(0, 1, 100)
        y = (X + 0.1 * np.random.randn(100) > 0.5).astype(int)
        cal = FastCalibrator(k=10)
        cal.fit(X, y)
        pred = cal.predict_proba(np.array([0.5]))
        assert 0 <= pred <= 1
        lower, upper = cal.confidence_interval(np.array([0.5]))
        assert lower <= pred <= upper

class TestFrictionPolicy:
    def test_rule_based_guardrails(self):
        policy = RuleBasedFrictionPolicy()
        state = {"gsr": 0.4, "bmc": 0.9, "fci": 0.9}
        assert policy.choose_action(state) == FrictionAction.SUGGEST_RECALIBRATION
        state = {"gsr": 0.9, "bmc": 0.5, "fci": 0.9}
        assert policy.choose_action(state) == FrictionAction.SUGGEST_ALTERNATIVE
        state = {"gsr": 0.9, "bmc": 0.9, "fci": 0.85}
        assert policy.choose_action(state) == FrictionAction.AUTO_CONFIRM

    def test_bandit_epsilon_greedy(self):
        policy = BanditFrictionPolicy(feature_names=["fci", "bmc"])
        state = {"fci": 0.9, "bmc": 0.8, "gsr": 0.9}
        policy._rng = np.random.RandomState(0)
        action = policy.choose_action(state)
        assert isinstance(action, FrictionAction)

class TestMetricsCollector:
    def test_in_memory_metrics(self):
        collector = InMemoryMetricsCollector()
        pid = "test1"
        collector.add_prediction(pid, {"fci_final": 0.9, "ci_width": 0.1})
        collector.add_outcome(pid, fit_success=True)
        pid2 = "test2"
        collector.add_prediction(pid2, {"fci_final": 0.4, "ci_width": 0.2})
        collector.add_outcome(pid2, fit_success=False, return_reason="too small")
        metrics = collector.compute_metrics()
        assert "brier_score" in metrics
        assert metrics["fit_return_rate"] == 0.5

    @patch('psycopg2.pool.SimpleConnectionPool')
    def test_postgres_collector(self, mock_pool):
        mock_conn = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        collector = PostgresMetricsCollector(mock_pool)
        collector.add_prediction("pid", {"fci_final": 0.8})
        collector.add_outcome("pid", True)

class TestFitConfidenceIndex:
    def test_pipeline_with_guardrails(self):
        body = BodyModel(bmc=0.5)  # below 0.6
        garment = GarmentModel(gsr=0.8, price_bucket=1, rigidity_index=0.5)
        brand = BrandData(bfs=0.7, brand_volatility=0.2)
        user = UserHistory(phfa=0.9, user_tolerance_index=0.5)
        fci = FitConfidenceIndex()
        result = fci.predict(body, garment, brand, user, "dress", "brandX", "user1")
        assert result["fci_final"] <= 0.75

    def test_pipeline_with_morphology_and_skin(self):
        morph = BodyMorphology(height_cm=170, weight_kg=70, chest_circumference=95, waist_circumference=75)
        skin = SkinProfile(fitzpatrick_type=FitzpatrickType.III, undertone=Undertone.NEUTRAL,
                           melanin_density=0.5, hydration_level=0.8)
        body = BodyModel(bmc=0.8, morphology=morph, skin=skin)
        garment = GarmentModel(gsr=0.8, price_bucket=1, rigidity_index=0.5, fabric_texture=0.3, breathability=0.7)
        brand = BrandData(bfs=0.7, brand_volatility=0.2)
        user = UserHistory(phfa=0.9, user_tolerance_index=0.5)
        # Use a dummy neural model that expects certain features
        class DummyModel:
            def predict(self, X):
                # Just return a small positive residual
                return np.array([0.02])
        neural = NeuralResidual(DummyModel(), ["bmc", "gsr", "bfs", "phfa", "s_struct", "s_bayes",
                                               "price_bucket", "rigidity", "brand_volatility", "user_tolerance",
                                               "fabric_texture", "breathability",
                                               "morph_height_cm", "morph_weight_kg", "morph_bmi",
                                               "morph_chest_circumference", "morph_waist_circumference",
                                               "skin_fitzpatrick", "skin_undertone",
                                               "skin_melanin_density", "skin_hydration_level"])
        fci = FitConfidenceIndex(neural_residual=neural)
        result = fci.predict(body, garment, brand, user, "dress", "brandX", "user1", prediction_id="test_morph")
        assert result["fci_final"] > 0
        assert result["delta_residual"] == 0.02

    def test_fallback_on_error(self):
        class BrokenModel:
            def predict(self, X):
                raise ValueError("broken")
        neural = NeuralResidual(BrokenModel(), ["bmc"])
        fci = FitConfidenceIndex(neural_residual=neural)
        body = BodyModel(bmc=0.8)
        garment = GarmentModel(gsr=0.8, price_bucket=1, rigidity_index=0.5)
        brand = BrandData(bfs=0.7, brand_volatility=0.2)
        user = UserHistory(phfa=0.9, user_tolerance_index=0.5)
        result = fci.predict(body, garment, brand, user, "dress", "brandX", "user1")
        assert "error" not in result
