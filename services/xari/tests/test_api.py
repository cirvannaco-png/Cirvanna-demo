from fastapi.testclient import TestClient

from app.main import app
from xari.routing import ROUTES, plan_route


def test_legacy_xari_entry_point_loads_the_canonical_pnelly_application():
    client = TestClient(app)
    response = client.get("/capabilities")
    assert response.status_code == 200
    assert app.title == "Cirvanna PNELLY API"
    assert response.json()["canonical_name"] == "PNELLY"
    assert response.json()["service"] == "cirvanna-pnelly"


def test_legacy_routing_import_is_the_same_canonical_route_contract():
    assert ROUTES["assistant_chat"].upstream_env == "PNELLY_CHAT_API_URL"
    legacy_url = plan_route("assistant_chat", {}, environment={
        "XARI_CHAT_API_URL": "https://legacy-xari.example.test",
    })
    assert legacy_url.configured is True
    assert legacy_url.code == "XARI_ROUTE_CONFIGURED_NOT_EXECUTED"
