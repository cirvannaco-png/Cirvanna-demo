"""
Privacy-first user data management with anonymization, encryption, and differential privacy.
"""
import hashlib
import time
from datetime import datetime
import orjson
import numpy as np

class PrivacyManager:
    def __init__(self, config):
        self.config = config
        self.anonymization_salt = b"xyra_privacy_salt_2026"

    def anonymize_user_id(self, user_id):
        if not self.config.ANONYMIZE_USER_IDS:
            return user_id
        anonymized = hashlib.blake2b(
            user_id.encode(),
            key=self.anonymization_salt,
            digest_size=16
        ).hexdigest()
        return anonymized

    def encrypt_sensitive_data(self, data):
        if not self.config.ENCRYPT_SENSITIVE_DATA:
            return orjson.dumps(data)
        serialized = orjson.dumps(data)
        encrypted = self.config.cipher.encrypt(serialized)
        return encrypted

    def decrypt_sensitive_data(self, encrypted_data):
        if not self.config.ENCRYPT_SENSITIVE_DATA:
            return orjson.loads(encrypted_data)
        decrypted = self.config.cipher.decrypt(encrypted_data)
        return orjson.loads(decrypted)

    def add_differential_privacy_noise(self, data, epsilon=None):
        if not self.config.ENABLE_DIFFERENTIAL_PRIVACY:
            return data
        epsilon = epsilon or self.config.DIFFERENTIAL_PRIVACY_EPSILON
        sensitivity = 1.0
        scale = sensitivity / epsilon
        noise = np.random.laplace(0, scale, data.shape)
        return data + noise

    def generate_audit_log(self, user_id, action, data):
        anonymized_id = self.anonymize_user_id(user_id)
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "anonymized_user_id": anonymized_id,
            "action": action,
            "data_type": type(data).__name__,
            "data_size": len(str(data)),
            "retention_days": self.config.DATA_RETENTION_DAYS,
        }
        log_entry["data_hash"] = hashlib.sha256(
            orjson.dumps(data)
        ).hexdigest()[:16]
        return log_entry
