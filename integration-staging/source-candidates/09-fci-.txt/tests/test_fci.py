import pytest
import numpy as np
from unittest.mock import MagicMock, patch
from src.fci.models import BodyModel, GarmentModel, BrandData, UserHistory
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

class TestBayesianLayer:
    def test_in_memory_update_and_predict(self):
        bayes = BayesianLayer()  # no redis
        bayes.update("dress", "brandA", "user1", successes=3, trials=5)
        bayes.update("dress", "brandA", "user1", successes=2, trials=3)
        # user level: 5/8 = 0.625, brand‑category prior = 5/8 as well (since no other users)
        # But brand‑category also updated from same data, so prior = 5/8, posterior = (5+5)/(8+8)=10/16=0.625
        pred = bayes.predict("dress", "brandA", "user1")
        assert pred == 5/8  # 0.625

    def test_redis_mocked(self):
        mock_redis = MagicMock()
        # mock hgetall to return empty initially, then after update return counts
        mock_redis.hgetall.return_value = {}  # empty
        bayes = BayesianLayer(redis_client=mock_redis)
        bayes.update("dress", "brandA", "user1", successes=3, trials=5)
        # check that redis calls were made
        mock_redis.hset.assert_called()  # at least once
        # For predict, we need to mock hgetall to return the stored counts
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
        state = {"fci": 0.9, "bmc": 0.8, "gsr": 0.9}  # gsr above threshold
        # With epsilon=0, always greedy; with random seed, predictable?
        policy._rng = np.random.RandomState(0)
        # first call may explore; we can't guarantee action, just test no crash
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
        assert metrics["fit_return_rate"] == 0.5  # one success out of two

    @patch('psycopg2.pool.SimpleConnectionPool')
    def test_postgres_collector(self, mock_pool):
        # This is a mock test; in real life you'd use a test database.
        mock_conn = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        collector = PostgresMetricsCollector(mock_pool)
        collector.add_prediction("pid", {"fci_final": 0.8})
        collector.add_outcome("pid", True)
        # Should not raise

class TestFitConfidenceIndex:
    def test_pipeline_with_guardrails(self):
        body = BodyModel(bmc=0.5)  # below 0.6
        garment = GarmentModel(gsr=0.8, price_bucket=1, rigidity_index=0.5)
        brand = BrandData(bfs=0.7, brand_volatility=0.2)
        user = UserHistory(phfa=0.9, user_tolerance_index=0.5)
        fci = FitConfidenceIndex()
        result = fci.predict(body, garment, brand, user, "dress", "brandX", "user1")
        # Guardrail: BMC < 0.6 => FCI <= 0.75
        assert result["fci_final"] <= 0.75

    def test_fallback_on_error(self):
        # Cause an error in neural residual
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
        assert "error" not in result  # error caught, fallback returned
