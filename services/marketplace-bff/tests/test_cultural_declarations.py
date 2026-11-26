from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app.cultural_declarations import (
    CulturalDeclarationCreateInput,
    CulturalDeclarationRetractionInput,
    create_cultural_declaration,
    declaration_id_for,
    list_cultural_declarations,
    retract_cultural_declaration,
)


class Response:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


class Client:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.responses.pop(0)

    async def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.responses.pop(0)


def create_payload(**overrides):
    data = {
        "request_id": "request-hard-coverage-001",
        "confirmation_version": "cultural-hard-requirements-v1",
        "user_confirmation": True,
        "requirements": [{
            "requirement_id": "coverage-long-sleeves",
            "attribute": "coverage:long-sleeves",
            "kind": "required_attribute",
            "hard": True,
        }],
    }
    data.update(overrides)
    return CulturalDeclarationCreateInput(**data)


def test_create_declaration_binds_verified_subject_and_only_hard_requirements():
    subject = "verified-user-42"
    declaration_id = declaration_id_for(subject, "request-hard-coverage-001")
    client = Client([Response({
        "user_id": subject,
        "declaration_id": declaration_id,
        "status": "active",
        "requirements": [{"attribute": "coverage:long-sleeves", "hard": True}],
    }, 201)])
    result = asyncio.run(create_cultural_declaration(
        client, base="https://cultural.example.test", token="internal-token",
        subject=subject, payload=create_payload(),
    ))
    sent = client.calls[0][2]["json"]
    assert sent["user_id"] == subject
    assert sent["declaration_id"] == declaration_id
    assert sent["requirements"][0]["hard"] is True
    assert result["hard_requirements"] is True


def test_create_requires_explicit_user_confirmation():
    with pytest.raises(HTTPException) as error:
        asyncio.run(create_cultural_declaration(
            Client([]), base="https://cultural.example.test", token="internal-token",
            subject="verified-user-42", payload=create_payload(user_confirmation=False),
        ))
    assert error.value.status_code == 400
    assert error.value.detail["code"] == "EXPLICIT_CULTURAL_CONFIRMATION_REQUIRED"


def test_create_rejects_soft_preferences_at_hard_policy_endpoint():
    with pytest.raises(HTTPException) as error:
        asyncio.run(create_cultural_declaration(
            Client([]), base="https://cultural.example.test", token="internal-token",
            subject="verified-user-42",
            payload=create_payload(requirements=[{
                "requirement_id": "coverage-long-sleeves",
                "attribute": "coverage:long-sleeves",
                "kind": "required_attribute",
                "hard": False,
            }]),
        ))
    assert error.value.status_code == 422


def test_list_declarations_is_scoped_to_verified_subject():
    subject = "verified-user-42"
    client = Client([Response({"user_id": subject, "declarations": []})])
    result = asyncio.run(list_cultural_declarations(
        client, base="https://cultural.example.test", token="internal-token", subject=subject,
    ))
    assert client.calls[0][2]["params"] == {"user_id": subject}
    assert result["declarations"] == []


def test_retraction_requires_confirmation_and_uses_idempotent_correction_id():
    subject = "verified-user-42"
    declaration_id = declaration_id_for(subject, "request-hard-coverage-001")
    client = Client([Response({
        "user_id": subject, "declaration_id": declaration_id, "status": "retracted",
    })])
    result = asyncio.run(retract_cultural_declaration(
        client, base="https://cultural.example.test", token="internal-token",
        subject=subject, declaration_id=declaration_id,
        payload=CulturalDeclarationRetractionInput(
            request_id="request-retract-coverage-001", user_confirmation=True,
        ),
    ))
    sent = client.calls[0][2]["json"]
    assert sent["user_id"] == subject
    assert sent["user_confirmation"] is True
    assert sent["correction_event_id"].startswith("cultural-correction-")
    assert result["status"] == "retracted"


def test_create_rejects_contradictory_required_and_forbidden_attributes():
    with pytest.raises(HTTPException) as error:
        asyncio.run(create_cultural_declaration(
            Client([]), base="https://cultural.example.test", token="internal-token",
            subject="verified-user-42",
            payload=create_payload(requirements=[
                {"requirement_id": "must-cover", "attribute": "coverage:long-sleeves", "kind": "required_attribute", "hard": True},
                {"requirement_id": "must-not-cover", "attribute": "coverage:long-sleeves", "kind": "forbidden_attribute", "hard": True},
            ]),
        ))
    assert error.value.status_code == 422
    assert error.value.detail["code"] == "CONTRADICTORY_CULTURAL_REQUIREMENTS"


def test_create_replay_confirms_exact_existing_declaration_before_success():
    subject = "verified-user-42"
    declaration_id = declaration_id_for(subject, "request-hard-coverage-001")
    client = Client([
        Response({"detail": "duplicate declaration"}, 409),
        Response({"user_id": subject, "declarations": [{
            "declaration_id": declaration_id,
            "status": "active",
            "requirements": [{
                "attribute": "coverage:long-sleeves",
                "kind": "required_attribute",
                "hard": True,
            }],
        }]}, 200),
    ])
    result = asyncio.run(create_cultural_declaration(
        client, base="https://cultural.example.test", token="internal-token",
        subject=subject, payload=create_payload(),
    ))
    assert result["idempotent_replay"] is True
    assert result["status"] == "active"
    assert len(client.calls) == 2
