import json
import numpy as np
from typing import Dict, List, Optional, Any
from datetime import datetime
import warnings

try:
    import psycopg2
    from psycopg2 import pool
    PSYCOPG2_AVAILABLE = True
except ImportError:
    psycopg2 = None
    PSYCOPG2_AVAILABLE = False
    warnings.warn("psycopg2 not installed. Metrics collector will use in‑memory storage.")

class MetricsCollector:
    """Base interface for metrics collection."""
    def add_prediction(self, prediction_id: str, result: Dict[str, Any]):
        raise NotImplementedError

    def add_outcome(self, prediction_id: str, fit_success: bool, return_reason: Optional[str] = None):
        raise NotImplementedError

    def compute_metrics(self) -> Dict[str, float]:
        raise NotImplementedError

class InMemoryMetricsCollector(MetricsCollector):
    """Simple in‑memory collector for testing."""
    def __init__(self):
        self.predictions = {}  # id -> result
        self.outcomes = {}     # id -> (success, reason)

    def add_prediction(self, prediction_id: str, result: Dict[str, Any]):
        self.predictions[prediction_id] = result

    def add_outcome(self, prediction_id: str, fit_success: bool, return_reason: Optional[str] = None):
        self.outcomes[prediction_id] = (fit_success, return_reason)

    def compute_metrics(self) -> Dict[str, float]:
        # Join predictions and outcomes
        ids = set(self.predictions.keys()) & set(self.outcomes.keys())
        if not ids:
            return {}
        y_true = []
        y_pred = []
        ci_widths = []
        for pid in ids:
            y_true.append(1 if self.outcomes[pid][0] else 0)
            y_pred.append(self.predictions[pid]["fci_final"])
            ci_widths.append(self.predictions[pid]["ci_width"])
        y_true = np.array(y_true)
        y_pred = np.array(y_pred)
        ci_widths = np.array(ci_widths)

        metrics = {}
        metrics["brier_score"] = float(np.mean((y_true - y_pred) ** 2))
        metrics["ece"] = self._expected_calibration_error(y_true, y_pred)
        metrics["mean_ci_width"] = float(np.mean(ci_widths))
        metrics["fit_return_rate"] = 1.0 - float(np.mean(y_true))
        metrics["false_confidence_rate"] = self._false_confidence_rate(y_true, y_pred, threshold=0.8)
        return metrics

    def _expected_calibration_error(self, y_true, y_pred, n_bins=10):
        bins = np.linspace(0, 1, n_bins + 1)
        bin_indices = np.digitize(y_pred, bins[1:-1])
        ece = 0.0
        for i in range(n_bins):
            mask = (bin_indices == i)
            if np.any(mask):
                bin_acc = np.mean(y_true[mask])
                bin_conf = np.mean(y_pred[mask])
                ece += np.abs(bin_acc - bin_conf) * np.sum(mask) / len(y_true)
        return float(ece)

    def _false_confidence_rate(self, y_true, y_pred, threshold=0.8):
        high_conf = y_pred >= threshold
        if not np.any(high_conf):
            return 0.0
        false_pos = np.sum((y_pred[high_conf] >= threshold) & (y_true[high_conf] == 0))
        return float(false_pos / np.sum(high_conf))

class PostgresMetricsCollector(MetricsCollector):
    """Persistent metrics collector using PostgreSQL."""
    def __init__(self, conn_pool: 'psycopg2.pool.SimpleConnectionPool'):
        self.pool = conn_pool
        self._init_db()

    def _init_db(self):
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS fci_predictions (
                        prediction_id TEXT PRIMARY KEY,
                        result JSONB,
                        created_at TIMESTAMP DEFAULT NOW()
                    );
                    CREATE TABLE IF NOT EXISTS fci_outcomes (
                        prediction_id TEXT PRIMARY KEY REFERENCES fci_predictions(prediction_id),
                        fit_success BOOLEAN,
                        return_reason TEXT,
                        created_at TIMESTAMP DEFAULT NOW()
                    );
                """)
                conn.commit()
        finally:
            self.pool.putconn(conn)

    def add_prediction(self, prediction_id: str, result: Dict[str, Any]):
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO fci_predictions (prediction_id, result) VALUES (%s, %s)",
                    (prediction_id, json.dumps(result))
                )
                conn.commit()
        finally:
            self.pool.putconn(conn)

    def add_outcome(self, prediction_id: str, fit_success: bool, return_reason: Optional[str] = None):
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO fci_outcomes (prediction_id, fit_success, return_reason) VALUES (%s, %s, %s)",
                    (prediction_id, fit_success, return_reason)
                )
                conn.commit()
        finally:
            self.pool.putconn(conn)

    def compute_metrics(self) -> Dict[str, float]:
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT p.result->>'fci_final' as fci,
                           p.result->>'ci_width' as ci_width,
                           o.fit_success
                    FROM fci_predictions p
                    JOIN fci_outcomes o ON p.prediction_id = o.prediction_id
                """)
                rows = cur.fetchall()
                if not rows:
                    return {}
                y_true = []
                y_pred = []
                ci_widths = []
                for row in rows:
                    y_true.append(1 if row[2] else 0)
                    y_pred.append(float(row[0]))
                    ci_widths.append(float(row[1]))
                y_true = np.array(y_true)
                y_pred = np.array(y_pred)
                ci_widths = np.array(ci_widths)
                # Compute metrics (same as in‑memory)
                collector = InMemoryMetricsCollector()  # reuse logic
                # We'd need to set its internal state; simpler: compute directly
                metrics = {}
                metrics["brier_score"] = float(np.mean((y_true - y_pred) ** 2))
                metrics["ece"] = collector._expected_calibration_error(y_true, y_pred)
                metrics["mean_ci_width"] = float(np.mean(ci_widths))
                metrics["fit_return_rate"] = 1.0 - float(np.mean(y_true))
                metrics["false_confidence_rate"] = collector._false_confidence_rate(y_true, y_pred, 0.8)
                return metrics
        finally:
            self.pool.putconn(conn)
