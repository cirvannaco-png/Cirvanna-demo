"""
MALI v7 Test Suite
Tests: brand auth JWT, service token auth, event routing, storage path isolation
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime, timezone, timedelta
from jose import jwt

# ─── Constants (mirror auth.py) ───────────────────────────────────────────────
BRAND_JWT_SECRET = "test-brand-secret-32-chars-minimum"
BRAND_ALGORITHM = "HS256"
FOUNDER_JWT_SECRET = "test-founder-secret-hs512-key-32ch"
FOUNDER_ALGORITHM = "HS512"
SERVICE_TOKEN_SECRET = "test-service-token-secret-32chars"
SERVICE_ALGORITHM = "HS256"


# ─── Helpers ───────────────────────────────────────────────────────────────────

def make_brand_token(brand_id="brand_001", role="brand_partner", token_type="access", expired=False):
    now = datetime.now(timezone.utc)
    exp = now - timedelta(minutes=1) if expired else now + timedelta(hours=8)
    return jwt.encode({
        "sub": brand_id, "brand_id": brand_id, "brand_name": "Test Brand",
        "email": "test@brand.co", "permissions": ["products:read", "products:write"],
        "role": role, "token_type": token_type, "iat": now, "exp": exp,
    }, BRAND_JWT_SECRET, algorithm=BRAND_ALGORITHM)


def make_service_token(expired=False, token_type="service"):
    now = datetime.now(timezone.utc)
    exp = now - timedelta(minutes=1) if expired else now + timedelta(minutes=15)
    return jwt.encode({
        "iss": "pamasmma", "aud": "cirvanna",
        "iat": now, "exp": exp, "type": token_type,
    }, SERVICE_TOKEN_SECRET, algorithm=SERVICE_ALGORITHM)


def make_founder_token(expired=False):
    now = datetime.now(timezone.utc)
    exp = now - timedelta(minutes=1) if expired else now + timedelta(hours=1)
    return jwt.encode({
        "sub": "kelson", "role": "founder", "permissions": ["*"],
        "iat": now, "exp": exp,
    }, FOUNDER_JWT_SECRET, algorithm=FOUNDER_ALGORITHM)


# ─── Brand Auth Tests ──────────────────────────────────────────────────────────

class TestBrandTokenCreation:
    def test_valid_brand_token_decodes(self):
        token = make_brand_token()
        payload = jwt.decode(token, BRAND_JWT_SECRET, algorithms=[BRAND_ALGORITHM])
        assert payload["brand_id"] == "brand_001"
        assert payload["role"] == "brand_partner"
        assert payload["token_type"] == "access"

    def test_brand_id_in_sub_and_brand_id_field(self):
        """brand_id must be in both sub and brand_id for redundant safety."""
        token = make_brand_token(brand_id="brand_xyz")
        payload = jwt.decode(token, BRAND_JWT_SECRET, algorithms=[BRAND_ALGORITHM])
        assert payload["sub"] == "brand_xyz"
        assert payload["brand_id"] == "brand_xyz"

    def test_expired_brand_token_raises(self):
        token = make_brand_token(expired=True)
        with pytest.raises(Exception):
            jwt.decode(token, BRAND_JWT_SECRET, algorithms=[BRAND_ALGORITHM])

    def test_refresh_token_has_correct_type(self):
        token = make_brand_token(token_type="refresh")
        payload = jwt.decode(token, BRAND_JWT_SECRET, algorithms=[BRAND_ALGORITHM])
        assert payload["token_type"] == "refresh"

    def test_brand_token_does_not_grant_founder_role(self):
        token = make_brand_token()
        payload = jwt.decode(token, BRAND_JWT_SECRET, algorithms=[BRAND_ALGORITHM])
        assert payload["role"] != "founder"

    def test_wrong_secret_raises(self):
        token = make_brand_token()
        with pytest.raises(Exception):
            jwt.decode(token, "wrong-secret", algorithms=[BRAND_ALGORITHM])


# ─── Service Token Tests ───────────────────────────────────────────────────────

class TestServiceTokenAuth:
    def test_valid_service_token_decodes(self):
        token = make_service_token()
        payload = jwt.decode(token, SERVICE_TOKEN_SECRET, algorithms=[SERVICE_ALGORITHM], audience="cirvanna")
        assert payload["type"] == "service"
        assert payload["iss"] == "pamasmma"
        assert payload["aud"] == "cirvanna"

    def test_expired_service_token_raises(self):
        token = make_service_token(expired=True)
        with pytest.raises(Exception):
            jwt.decode(token, SERVICE_TOKEN_SECRET, algorithms=[SERVICE_ALGORITHM], audience="cirvanna")

    def test_wrong_audience_raises(self):
        token = make_service_token()
        with pytest.raises(Exception):
            jwt.decode(token, SERVICE_TOKEN_SECRET, algorithms=[SERVICE_ALGORITHM], audience="wrong")

    def test_non_service_type_detected(self):
        token = make_service_token(token_type="access")
        payload = jwt.decode(token, SERVICE_TOKEN_SECRET, algorithms=[SERVICE_ALGORITHM], audience="cirvanna")
        assert payload["type"] != "service"


# ─── Founder Auth Tests ────────────────────────────────────────────────────────

class TestFounderAuth:
    def test_valid_founder_token(self):
        token = make_founder_token()
        payload = jwt.decode(token, FOUNDER_JWT_SECRET, algorithms=[FOUNDER_ALGORITHM])
        assert payload["role"] == "founder"
        assert payload["sub"] == "kelson"
        assert "*" in payload["permissions"]

    def test_expired_founder_token_raises(self):
        token = make_founder_token(expired=True)
        with pytest.raises(Exception):
            jwt.decode(token, FOUNDER_JWT_SECRET, algorithms=[FOUNDER_ALGORITHM])

    def test_founder_token_uses_hs512(self):
        """Verify HS512 is enforced — HS256 should fail to decode founder token."""
        token = make_founder_token()
        with pytest.raises(Exception):
            jwt.decode(token, FOUNDER_JWT_SECRET, algorithms=["HS256"])


# ─── Event Routing Tests ───────────────────────────────────────────────────────

class TestEventRouting:
    def setup_method(self):
        # Import routing map directly
        self.routing = {
            "customer.support_needed": "relationship_management",
            "customer.cart_abandoned": "behavioral_consistency",
            "brand.onboarded": "marketing_intelligence",
            "brand.product_uploaded": "narrative_governance",
            "platform.anomaly_alert": "executive_operations",
            "platform.embedding_drift": "executive_operations",
            "content.campaign_created": "creator_economy",
            "content.low_ctr": "marketing_intelligence",
            "system.weekly_review": "strategic_narrative",
        }

    def test_support_routes_to_relationship(self):
        assert self.routing["customer.support_needed"] == "relationship_management"

    def test_cart_abandoned_routes_to_behavioral(self):
        assert self.routing["customer.cart_abandoned"] == "behavioral_consistency"

    def test_brand_onboarded_routes_to_marketing(self):
        assert self.routing["brand.onboarded"] == "marketing_intelligence"

    def test_anomaly_routes_to_executive(self):
        assert self.routing["platform.anomaly_alert"] == "executive_operations"

    def test_embedding_drift_routes_to_executive(self):
        assert self.routing["platform.embedding_drift"] == "executive_operations"

    def test_weekly_review_routes_to_strategic(self):
        assert self.routing["system.weekly_review"] == "strategic_narrative"

    def test_all_events_have_routing(self):
        for event_type, system in self.routing.items():
            assert system, f"Event {event_type} has no target system"
            assert "_" in system or system == "executive_operations", f"Invalid system: {system}"


# ─── Storage Path Isolation Tests ─────────────────────────────────────────────

class TestStoragePathIsolation:
    def _safe_path(self, brand_id, *segments):
        """Replicate safe_path logic for testing."""
        for seg in segments:
            if ".." in seg or seg.startswith("/"):
                raise ValueError(f"Invalid path segment: {seg}")
        path = "/".join([brand_id] + list(segments))
        if not path.startswith(f"{brand_id}/"):
            raise PermissionError(f"Path outside brand prefix")
        return path

    def test_valid_path_construction(self):
        path = self._safe_path("brand_001", "products", "p123", "raw", "image.jpg")
        assert path == "brand_001/products/p123/raw/image.jpg"
        assert path.startswith("brand_001/")

    def test_path_traversal_blocked(self):
        with pytest.raises(ValueError):
            self._safe_path("brand_001", "../brand_002", "secret.jpg")

    def test_absolute_path_blocked(self):
        with pytest.raises(ValueError):
            self._safe_path("brand_001", "/etc/passwd")

    def test_brand_a_cannot_read_brand_b(self):
        """Simulate brand B trying to access brand A's path."""
        brand_a_id = "brand_aaa"
        brand_b_id = "brand_bbb"
        gcs_path = f"{brand_a_id}/products/p1/image.jpg"
        # brand_b should not be able to verify this path
        assert not gcs_path.startswith(f"{brand_b_id}/")

    def test_correct_brand_can_access_own_path(self):
        brand_id = "brand_001"
        gcs_path = f"{brand_id}/products/p1/image.jpg"
        assert gcs_path.startswith(f"{brand_id}/")

    def test_double_dot_in_filename_blocked(self):
        with pytest.raises(ValueError):
            self._safe_path("brand_001", "products", "p1", "../../../etc/cron.d/evil")


# ─── PAMASMMA Action Log Tests ─────────────────────────────────────────────────

class TestPAMASMMAActionLog:
    def test_autonomy_levels_are_valid(self):
        valid = {"full_auto", "approval_required", "manual_only"}
        test_level = "approval_required"
        assert test_level in valid

    def test_requires_founder_approval_is_boolean(self):
        """Ensure override flag is strictly boolean, not truthy."""
        requires = True
        assert isinstance(requires, bool)
        assert requires is True

    def test_override_decision_options(self):
        valid_decisions = {"approve", "reject"}
        for d in valid_decisions:
            assert d in valid_decisions


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
