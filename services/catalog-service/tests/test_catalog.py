import os

os.environ.setdefault("CATALOG_DATABASE_URL", "sqlite://")
os.environ.setdefault("CATALOG_AUTO_CREATE_SCHEMA", "false")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import Base, app, get_db

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
    Base.metadata.drop_all(bind=TEST_ENGINE)
    Base.metadata.create_all(bind=TEST_ENGINE)
    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setenv("CATALOG_API_TOKEN", "catalog-test-token")
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


def test_readiness_reports_database_and_auth_state(client, monkeypatch):
    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["database_connected"] is True
    assert ready.json()["authentication_configured"] is True
    assert ready.json()["ready"] is True

    monkeypatch.delenv("CATALOG_API_TOKEN")
    not_ready = client.get("/ready")
    assert not_ready.status_code == 200
    assert not_ready.json()["ready"] is False
