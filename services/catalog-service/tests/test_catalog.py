import os

os.environ.setdefault("CATALOG_DATABASE_URL", "sqlite://")
os.environ.setdefault("CATALOG_AUTO_CREATE_SCHEMA", "false")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import Base, ProductVersion, app, get_db

TEST_ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(bind=TEST_ENGINE, autoflush=False, autocommit=False, expire_on_commit=False)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch):
    with TEST_ENGINE.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    Base.metadata.drop_all(bind=TEST_ENGINE)
    Base.metadata.create_all(bind=TEST_ENGINE)
    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setenv("CATALOG_API_TOKEN", "catalog-test-token")
    monkeypatch.setenv("CATALOG_ENVIRONMENT", "development")
    monkeypatch.delenv("CATALOG_READ_TOKEN", raising=False)
    monkeypatch.delenv("CATALOG_WRITE_TOKEN", raising=False)
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def auth_headers():
    return {"Authorization": "Bearer catalog-test-token"}


def product_payload(**overrides):
    value = {
        "sku": "glow-001",
        "name": "Hydrating Lip Gloss",
        "description": "A sheer gloss.",
        "category": "beauty",
        "brand": "Demo Brand",
        "price_minor": 1250,
        "currency": "KES",
        "attributes": {"finish": "glossy", "shade": "rose"},
        "image_urls": ["https://cdn.example.test/products/glow-001.webp"],
    }
    value.update(overrides)
    return value


def create_product(client, **overrides):
    response = client.post(
        "/products", headers=auth_headers(), json=product_payload(**overrides)
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_production_requires_distinct_read_and_write_catalog_credentials(client, monkeypatch):
    monkeypatch.setenv("CATALOG_ENVIRONMENT", "production")
    monkeypatch.delenv("CATALOG_API_TOKEN", raising=False)
    monkeypatch.setenv("CATALOG_READ_TOKEN", "catalog-production-read-only-secret")
    monkeypatch.setenv("CATALOG_WRITE_TOKEN", "catalog-production-write-only-secret")

    write_headers = {"Authorization": "Bearer catalog-production-write-only-secret"}
    read_headers = {"Authorization": "Bearer catalog-production-read-only-secret"}
    product_response = client.post("/products", headers=write_headers, json=product_payload())
    assert product_response.status_code == 201
    product_id = product_response.json()["product_id"]

    assert client.get("/products/" + product_id, headers=read_headers).status_code == 200
    assert client.get("/products/" + product_id, headers=write_headers).status_code == 401
    assert client.post("/products", headers=read_headers, json=product_payload(sku="READ-ONLY-001")).status_code == 401
    assert client.patch(
        "/products/" + product_id,
        headers=read_headers,
        json={"name": "Should Not Update"},
    ).status_code == 401
    assert client.patch(
        "/products/" + product_id,
        headers=write_headers,
        json={"name": "Privileged Update"},
    ).status_code == 200

    # A single shared credential is explicitly rejected in production.
    monkeypatch.setenv("CATALOG_WRITE_TOKEN", "catalog-production-read-only-secret")
    assert client.get("/ready").status_code == 503


def test_health_is_liveness_only(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "alive"


def test_capabilities_are_explicit_about_missing_commerce_features(client):
    capabilities = client.get("/capabilities").json()
    assert capabilities["canonical_product_identity"] is True
    assert capabilities["catalog_persistence"] is True
    assert capabilities["product_version_history"] is True
    assert capabilities["checkout"] is False
    assert capabilities["payments"] is False
    assert capabilities["fit_prediction"] is False
    assert capabilities["click_it_reconstruction"] is False


def test_all_catalog_mutations_require_authentication(client):
    response = client.post("/products", json=product_payload())
    assert response.status_code == 401


def test_create_normalizes_sku_and_records_initial_version(client):
    product = create_product(client)
    assert product["sku"] == "GLOW-001"
    assert product["catalog_version"] == 1
    assert product["status"] == "active"
    assert product["attributes"]["shade"] == "rose"

    history = client.get(
        f"/products/{product['product_id']}/versions", headers=auth_headers()
    )
    assert history.status_code == 200
    assert len(history.json()) == 1
    assert history.json()[0]["change_type"] == "created"
    assert history.json()[0]["catalog_version"] == 1


def test_duplicate_sku_is_a_conflict_even_if_case_differs(client):
    create_product(client, sku="sku-duplicate")
    response = client.post(
        "/products",
        headers=auth_headers(),
        json=product_payload(sku="SKU-DUPLICATE"),
    )
    assert response.status_code == 409


def test_invalid_currency_and_non_http_image_url_are_rejected(client):
    response = client.post(
        "/products",
        headers=auth_headers(),
        json=product_payload(currency="K"),
    )
    assert response.status_code == 422

    response = client.post(
        "/products",
        headers=auth_headers(),
        json=product_payload(sku="GLOW-002", image_urls=["javascript:alert(1)"]),
    )
    assert response.status_code == 422


def test_patch_increments_version_and_rejects_stale_writer(client):
    product = create_product(client)
    response = client.patch(
        f"/products/{product['product_id']}?expected_version=1",
        headers=auth_headers(),
        json={"name": "Hydrating Lip Gloss - Rose"},
    )
    assert response.status_code == 200
    assert response.json()["catalog_version"] == 2

    stale = client.patch(
        f"/products/{product['product_id']}?expected_version=1",
        headers=auth_headers(),
        json={"price_minor": 1400},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "STALE_CATALOG_VERSION"

    history = client.get(
        f"/products/{product['product_id']}/versions", headers=auth_headers()
    ).json()
    assert [item["catalog_version"] for item in history] == [1, 2]
    assert history[1]["snapshot"]["name"] == "Hydrating Lip Gloss - Rose"


def test_list_search_pagination_and_active_default(client):
    create_product(client, sku="GLOW-010", name="Rose Lipstick", category="makeup")
    create_product(client, sku="CARE-011", name="Daily Cleanser", category="skincare")
    response = client.get(
        "/products?q=rose&limit=1", headers=auth_headers()
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["name"] == "Rose Lipstick"


def test_delete_archives_without_erasing_history(client):
    product = create_product(client)
    response = client.delete(
        f"/products/{product['product_id']}?expected_version=1",
        headers=auth_headers(),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "archived"
    assert response.json()["catalog_version"] == 2

    active = client.get("/products", headers=auth_headers()).json()
    archived = client.get(
        "/products?status=archived", headers=auth_headers()
    ).json()
    assert active["total"] == 0
    assert archived["total"] == 1

    history = client.get(
        f"/products/{product['product_id']}/versions", headers=auth_headers()
    ).json()
    assert [item["change_type"] for item in history] == ["created", "archived"]


def test_batch_product_lookup_is_read_only_bounded_and_excludes_archived(client):
    active = create_product(
        client,
        sku="BATCH-ACTIVE-001",
        description="Breathable cotton linen blend for summer.",
    )
    archived = create_product(client, sku="BATCH-ARCHIVED-002", name="Archived garment")
    archive_response = client.delete(
        f"/products/{archived['product_id']}", headers=auth_headers()
    )
    assert archive_response.status_code == 200

    query = f"/products/batch?ids={active['product_id']}&ids={archived['product_id']}"
    unauthorized = client.get(query)
    assert unauthorized.status_code == 401

    response = client.get(query, headers=auth_headers())
    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["product_id"] for item in body["items"]] == [active["product_id"]]
    assert body["items"][0]["description"] == "Breathable cotton linen blend for summer."


def test_catalog_keyword_search_includes_product_descriptions(client):
    create_product(
        client,
        sku="DETAIL-SEARCH-003",
        name="Everyday top",
        description="Soft indigo chambray with a relaxed cut.",
    )
    response = client.get("/products?q=chambray", headers=auth_headers())
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["name"] == "Everyday top"


def test_readiness_requires_current_migration_and_auth_config(client, monkeypatch):
    pending = client.get("/ready")
    assert pending.status_code == 503
    pending_detail = pending.json()["detail"]
    assert pending_detail["database_connected"] is True
    assert pending_detail["schema_present"] is True
    assert pending_detail["migrations_required"] is True
    assert pending_detail["migrations_applied"] is False
    assert pending_detail["ready"] is False

    with TEST_ENGINE.begin() as connection:
        connection.execute(text(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
        ))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": "20261104_0002"},
        )

    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["database_connected"] is True
    assert ready.json()["schema_present"] is True
    assert ready.json()["migrations_required"] is True
    assert ready.json()["migrations_applied"] is True
    assert ready.json()["schema_revision"] == "20261104_0002"
    assert ready.json()["authentication_configured"] is True
    assert ready.json()["ready"] is True

    monkeypatch.delenv("CATALOG_API_TOKEN")
    not_ready = client.get("/ready")
    assert not_ready.status_code == 503
    assert not_ready.json()["detail"]["ready"] is False


def test_product_intelligence_metadata_is_validated_and_versioned(client):
    metadata = {
        "schema_version": "1.0",
        "climate_compatibility": {
            "compatible_conditions": ["hot_humid", "temperate"],
            "evidence": {
                "source_type": "manufacturer_declared",
                "reference": "merchant-spec-sheet-2026-01",
                "reviewed_at": "2026-10-31",
            },
        },
        "context_usage": {
            "intended_contexts": ["daily", "evening"],
            "evidence": {
                "source_type": "merchant_catalogued",
                "reference": "catalog-editorial-record-22",
                "reviewed_at": "2026-10-31",
            },
        },
        "cultural_usage": {
            "declared_tags": ["user-selected formal celebration styling"],
            "editorial_reviewed": True,
            "evidence": {
                "source_type": "editorially_reviewed",
                "reference": "editorial-review-2026-08",
                "reviewed_at": "2026-10-31",
            },
        },
        "skin_response": {
            "ingredient_labels": ["glycerin", "squalane"],
            "cosmetic_intent_tags": ["hydration", "soft finish"],
            "caution_labels": [],
            "evidence": {
                "source_type": "manufacturer_declared",
                "reference": "ingredient-label-batch-04",
                "reviewed_at": "2026-10-31",
            },
        },
        "appearance_complement": {
            "shade_families": ["warm rose", "neutral rose"],
            "undertone_matches": ["warm", "neutral"],
            "finishes": ["satin"],
            "pairing_colors": ["navy", "cream"],
            "feature_complement_tags": ["soft contrast"],
            "evidence": {
                "source_type": "merchant_catalogued",
                "reference": "shade-review-2026-11",
                "reviewed_at": "2026-10-31",
            },
        },
        "observed_outcomes": {
            "metric": "reported_satisfaction",
            "value": 0.82,
            "sample_size": 45,
            "observation_window_days": 180,
            "evidence": {
                "source_type": "consented_aggregate",
                "reference": "aggregate-feedback-report-2026-10",
                "reviewed_at": "2026-10-31",
            },
            "limitations": "Self-reported cosmetic satisfaction; this does not establish causal efficacy.",
        },
    }
    product = create_product(client, attributes={"product_intelligence": metadata, "finish": "satin"})
    intelligence = product["attributes"]["product_intelligence"]
    assert intelligence["climate_compatibility"]["compatible_conditions"] == ["hot_humid", "temperate"]
    assert intelligence["cultural_usage"]["editorial_reviewed"] is True
    assert intelligence["observed_outcomes"]["sample_size"] == 45

    # Customer-facing reads fail closed until the durable CIL gateway validates rights.
    history = client.get(
        f"/products/{product['product_id']}/versions", headers=auth_headers()
    )
    assert history.status_code == 200
    assert "product_intelligence" not in history.json()[0]["snapshot"]["attributes"]

    # Catalog still retains the immutable versioned record internally.
    db = TestSessionLocal()
    try:
        version = db.query(ProductVersion).filter_by(product_id=product["product_id"]).one()
        assert version.snapshot["attributes"]["product_intelligence"]["schema_version"] == "1.0"
    finally:
        db.close()


def test_cultural_product_metadata_requires_editorial_review_evidence(client):
    invalid = {
        "schema_version": "1.0",
        "cultural_usage": {
            "declared_tags": ["festival styling"],
            "editorial_reviewed": False,
            "evidence": {
                "source_type": "merchant_catalogued",
                "reference": "unreviewed-merchant-copy",
                "reviewed_at": "2026-10-31",
            },
        },
    }
    response = client.post(
        "/products",
        headers=auth_headers(),
        json=product_payload(sku="CULTURE-INVALID-01", attributes={"product_intelligence": invalid}),
    )
    assert response.status_code == 422


def test_historical_outcomes_require_minimum_aggregate_sample_and_provenance(client):
    invalid = {
        "schema_version": "1.0",
        "observed_outcomes": {
            "metric": "reported_satisfaction",
            "value": 0.95,
            "sample_size": 4,
            "observation_window_days": 90,
            "evidence": {
                "source_type": "consented_aggregate",
                "reference": "tiny-cohort",
                "reviewed_at": "2026-10-31",
            },
            "limitations": "Small sample is not generalisable and should not be shown as a product success rate.",
        },
    }
    response = client.post(
        "/products",
        headers=auth_headers(),
        json=product_payload(sku="OUTCOME-INVALID-01", attributes={"product_intelligence": invalid}),
    )
    assert response.status_code == 422


def test_legacy_product_attributes_remain_backward_compatible(client):
    product = create_product(client, sku="LEGACY-ATTR-001", attributes={"finish": "matte", "shade": "plum"})
    assert product["attributes"] == {"finish": "matte", "shade": "plum"}

def test_canonical_variants_are_catalog_owned_normalized_and_immutable(client):
    product = create_product(client, sku="VARIANT-PRODUCT-001")
    product_id = product["product_id"]

    created = client.post(
        f"/products/{product_id}/variants",
        headers=auth_headers(),
        json={"attributes": {" Size ": " Medium ", "Colour": " BLUE "}},
    )
    assert created.status_code == 201, created.text
    variant = created.json()
    assert variant["product_id"] == product_id
    assert variant["attributes"] == {"colour": "blue", "size": "medium"}
    assert len(variant["variant_id"]) == 36

    duplicate = client.post(
        f"/products/{product_id}/variants",
        headers=auth_headers(),
        json={"attributes": {"colour": "Blue", "size": "MEDIUM"}},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "CANONICAL_VARIANT_ALREADY_EXISTS"

    distinct = client.post(
        f"/products/{product_id}/variants",
        headers=auth_headers(),
        json={"attributes": {"colour": "blue", "size": "large"}},
    )
    assert distinct.status_code == 201
    assert distinct.json()["variant_id"] != variant["variant_id"]

    fetched = client.get(f"/variants/{variant['variant_id']}", headers=auth_headers())
    assert fetched.status_code == 200
    assert fetched.json()["variant_id"] == variant["variant_id"]

    listed = client.get(f"/products/{product_id}/variants", headers=auth_headers())
    assert listed.status_code == 200
    assert listed.json()["total"] == 2


def test_canonical_variant_routes_require_scoped_catalog_credentials(client):
    product = create_product(client, sku="VARIANT-AUTH-001")
    product_id = product["product_id"]
    assert client.post(
        f"/products/{product_id}/variants",
        json={"attributes": {"size": "small"}},
    ).status_code == 401
    created = client.post(
        f"/products/{product_id}/variants",
        headers=auth_headers(),
        json={"attributes": {"size": "small"}},
    )
    assert created.status_code == 201
    assert client.get(f"/variants/{created.json()['variant_id']}").status_code == 401


def test_archived_canonical_variant_is_hidden_and_identity_cannot_be_reissued(client):
    product = create_product(client, sku="VARIANT-ARCHIVE-001")
    product_id = product["product_id"]
    created = client.post(
        f"/products/{product_id}/variants",
        headers=auth_headers(),
        json={"attributes": {"size": "medium", "colour": "blue"}},
    )
    assert created.status_code == 201
    variant_id = created.json()["variant_id"]

    archived = client.delete(f"/variants/{variant_id}", headers=auth_headers())
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert archived.json()["variant_version"] == 2
    assert client.get(f"/variants/{variant_id}", headers=auth_headers()).status_code == 404
    assert client.get(f"/products/{product_id}/variants", headers=auth_headers()).json()["total"] == 0

    duplicate = client.post(
        f"/products/{product_id}/variants",
        headers=auth_headers(),
        json={"attributes": {"size": "medium", "colour": "blue"}},
    )
    assert duplicate.status_code == 409


def test_cil_metadata_is_removed_from_product_get_when_gateway_is_not_configured(client, monkeypatch):
    monkeypatch.delenv("CIL_GATEWAY_URL", raising=False)
    monkeypatch.delenv("CIL_SERVICE_TOKEN", raising=False)
    metadata = {
        "schema_version": "1.0",
        "claims": [{
            "claim_id": "CLAIM-001",
            "claim_type": "cosmetic_intent",
            "statement": "A cosmetic formulation claim awaiting review.",
            "evidence": {
                "source_type": "manufacturer_declared",
                "reference": "evidence-001",
                "reviewed_at": "2026-11-10",
                "source_id": "source-001",
                "evidence_grade": "E4",
                "scope": "finished_product",
            },
            "review_status": "pending_review",
            "limitations": "This is not independent clinical efficacy evidence.",
        }],
    }
    product = create_product(
        client,
        sku="CIL-GATE-001",
        attributes={"product_intelligence": metadata, "finish": "satin"},
    )
    response = client.get(f"/products/{product['product_id']}", headers=auth_headers())
    assert response.status_code == 200
    assert response.json()["attributes"]["finish"] == "satin"
    assert "product_intelligence" not in response.json()["attributes"]


def test_cil_gateway_can_serve_validated_ingredient_with_attribution(client, monkeypatch):
    from app import main as catalog_main

    monkeypatch.setenv("CIL_GATEWAY_URL", "https://cil.internal")
    monkeypatch.setenv("CIL_CATALOG_SERVICE_TOKEN", "catalog-to-cil-token")

    class FakeResponse:
        def __init__(self, request_payload):
            self.request_payload = request_payload
        def raise_for_status(self):
            return None
        def json(self):
            return {
                "product_id": self.request_payload["product_id"],
                "catalog_version": self.request_payload["catalog_version"],
                "all_eligible": True,
                "decisions": [{
                    "item_id": "Glycerin", "kind": "ingredient", "eligible": True,
                    "attribution_required": True, "attribution_text": "Manufacturer label",
                    "source_owner": "Manufacturer",
                }],
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None
        async def post(self, url, json, headers):
            assert url == "https://cil.internal/serving/assessment"
            assert headers["Authorization"] == "Bearer catalog-to-cil-token"
            return FakeResponse(json)

    monkeypatch.setattr(catalog_main.httpx, "AsyncClient", FakeAsyncClient)
    metadata = {
        "schema_version": "1.0",
        "ingredient_declarations": [{
            "inci_name": "Glycerin",
            "label_order": 2,
            "evidence": {
                "source_type": "manufacturer_declared",
                "reference": "cil-evidence-001",
                "reviewed_at": "2026-11-10",
                "source_id": "cil-source-001",
                "evidence_grade": "E4",
                "scope": "finished_product",
            },
        }],
    }
    product = create_product(
        client, sku="CIL-GATE-APPROVED-001",
        attributes={"product_intelligence": metadata},
    )
    response = client.get(f"/products/{product['product_id']}", headers=auth_headers())
    assert response.status_code == 200
    intelligence = response.json()["attributes"]["product_intelligence"]
    assert intelligence["ingredient_declarations"][0]["evidence"]["attribution"] == "Manufacturer label"
