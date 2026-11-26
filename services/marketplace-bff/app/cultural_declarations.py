"""Authenticated BFF adapter for explicit, auditable Cultural Identity declarations.

This module transports user-confirmed hard requirements to the canonical Cultural
Identity service. It does not infer requirements or implement policy evaluation.
"""
from __future__ import annotations

import hashlib
import re
from typing import Literal

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator


class CulturalRequirementInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirement_id: str = Field(min_length=1, max_length=128)
    attribute: str = Field(min_length=1, max_length=160)
    kind: Literal["required_attribute", "forbidden_attribute"]
    hard: bool = True


class CulturalDeclarationCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=8, max_length=128)
    confirmation_version: str = Field(min_length=1, max_length=80)
    user_confirmation: bool
    requirements: list[CulturalRequirementInput] = Field(min_length=1, max_length=60)

    @field_validator("request_id")
    @classmethod
    def normalize_request_id(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}", value):
            raise ValueError("request_id must use the controlled opaque ID format")
        return value


class CulturalDeclarationRetractionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=8, max_length=128)
    user_confirmation: bool

    @field_validator("request_id")
    @classmethod
    def normalize_request_id(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}", value):
            raise ValueError("request_id must use the controlled opaque ID format")
        return value


def declaration_id_for(subject: str, request_id: str) -> str:
    digest = hashlib.sha256(f"{subject}|{request_id}".encode("utf-8")).hexdigest()[:32]
    return "cultural-" + digest


def correction_event_id_for(subject: str, declaration_id: str, request_id: str) -> str:
    digest = hashlib.sha256(
        f"{subject}|{declaration_id}|{request_id}".encode("utf-8")
    ).hexdigest()[:32]
    return "cultural-correction-" + digest


def _validate_service_response(data: object, *, subject: str) -> dict:
    if not isinstance(data, dict) or data.get("user_id") != subject:
        raise HTTPException(502, detail={"code": "CULTURAL_DECLARATION_RESPONSE_SCOPE_INVALID"})
    return data


async def create_cultural_declaration(
    client: httpx.AsyncClient, *, base: str, token: str, subject: str,
    payload: CulturalDeclarationCreateInput,
) -> dict:
    if payload.user_confirmation is not True:
        raise HTTPException(400, detail={"code": "EXPLICIT_CULTURAL_CONFIRMATION_REQUIRED"})
    if any(not item.hard for item in payload.requirements):
        raise HTTPException(422, detail={"code": "CULTURAL_DECLARATION_ENDPOINT_ACCEPTS_HARD_REQUIREMENTS_ONLY"})
    if len({item.requirement_id for item in payload.requirements}) != len(payload.requirements):
        raise HTTPException(422, detail={"code": "DUPLICATE_CULTURAL_REQUIREMENT_ID"})
    declaration_id = declaration_id_for(subject, payload.request_id)
    body = {
        "user_id": subject,
        "declaration_id": declaration_id,
        "confirmation_version": payload.confirmation_version,
        "user_confirmation": True,
        "requirements": [item.model_dump() for item in payload.requirements],
    }
    try:
        response = await client.post(
            base + "/v1/declarations",
            headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
            json=body,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "CULTURAL_DECLARATION_SERVICE_UNAVAILABLE"}) from exc
    if response.status_code == 409:
        raise HTTPException(409, detail={"code": "CULTURAL_DECLARATION_CONFLICT"})
    if response.status_code != 201:
        raise HTTPException(503, detail={"code": "CULTURAL_DECLARATION_CREATE_FAILED"})
    try:
        data = _validate_service_response(response.json(), subject=subject)
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "CULTURAL_DECLARATION_RESPONSE_INVALID"}) from exc
    if data.get("declaration_id") != declaration_id or data.get("status") != "active":
        raise HTTPException(502, detail={"code": "CULTURAL_DECLARATION_RESPONSE_INVALID"})
    return {
        "declaration_id": declaration_id,
        "status": "active",
        "requirements": data.get("requirements", []),
        "policy_owner": "Cultural Identity",
        "hard_requirements": True,
    }


async def list_cultural_declarations(
    client: httpx.AsyncClient, *, base: str, token: str, subject: str,
) -> dict:
    try:
        response = await client.get(
            base + "/v1/declarations",
            params={"user_id": subject},
            headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
        )
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "CULTURAL_DECLARATION_SERVICE_UNAVAILABLE"}) from exc
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "CULTURAL_DECLARATION_LIST_FAILED"})
    try:
        data = _validate_service_response(response.json(), subject=subject)
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "CULTURAL_DECLARATION_RESPONSE_INVALID"}) from exc
    if not isinstance(data.get("declarations"), list):
        raise HTTPException(502, detail={"code": "CULTURAL_DECLARATION_RESPONSE_INVALID"})
    return {"user_id": subject, "declarations": data["declarations"], "policy_owner": "Cultural Identity"}


async def retract_cultural_declaration(
    client: httpx.AsyncClient, *, base: str, token: str, subject: str,
    declaration_id: str, payload: CulturalDeclarationRetractionInput,
) -> dict:
    if payload.user_confirmation is not True:
        raise HTTPException(400, detail={"code": "EXPLICIT_CULTURAL_RETRACTION_CONFIRMATION_REQUIRED"})
    if not re.fullmatch(r"cultural-[0-9a-f]{32}", declaration_id):
        raise HTTPException(422, detail={"code": "INVALID_CULTURAL_DECLARATION_ID"})
    correction_id = correction_event_id_for(subject, declaration_id, payload.request_id)
    try:
        response = await client.post(
            base + f"/v1/declarations/{declaration_id}/retract",
            headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
            json={"user_id": subject, "correction_event_id": correction_id, "user_confirmation": True},
        )
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "CULTURAL_DECLARATION_SERVICE_UNAVAILABLE"}) from exc
    if response.status_code == 404:
        raise HTTPException(404, detail={"code": "CULTURAL_DECLARATION_NOT_FOUND"})
    if response.status_code == 409:
        raise HTTPException(409, detail={"code": "CULTURAL_DECLARATION_CONFLICT"})
    if response.status_code != 200:
        raise HTTPException(503, detail={"code": "CULTURAL_DECLARATION_RETRACTION_FAILED"})
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "CULTURAL_DECLARATION_RESPONSE_INVALID"}) from exc
    if not isinstance(data, dict) or data.get("user_id") != subject or data.get("declaration_id") != declaration_id:
        raise HTTPException(502, detail={"code": "CULTURAL_DECLARATION_RESPONSE_SCOPE_INVALID"})
    return {"declaration_id": declaration_id, "status": data.get("status", "retracted"), "policy_owner": "Cultural Identity"}
