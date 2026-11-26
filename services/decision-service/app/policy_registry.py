"""Server-authoritative, version-pinned EEPL policy resolver."""
from __future__ import annotations

import json
import os
from typing import Any

_REQUIRED = {
    "policy_version", "minimum_age", "maximum_age", "allowed_locations",
    "allowed_occasions", "allowed_climates", "required_context",
}


class PolicyRegistryError(ValueError):
    pass


def resolve_policy(policy_id: str, policy_version: str) -> dict[str, Any]:
    raw = os.getenv("EEPL_POLICY_REGISTRY_JSON", "").strip()
    if not raw:
        raise PolicyRegistryError("server policy registry is not configured")
    try:
        registry = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PolicyRegistryError("server policy registry is invalid JSON") from exc
    if not isinstance(registry, dict):
        raise PolicyRegistryError("server policy registry must be an object")
    entry = registry.get(policy_id)
    if not isinstance(entry, dict) or set(entry) != _REQUIRED:
        raise PolicyRegistryError("policy is not registered on this server")
    if entry.get("policy_version") != policy_version:
        raise PolicyRegistryError("policy version is not the active server version")
    if entry.get("minimum_age") is not None and type(entry["minimum_age"]) is not int:
        raise PolicyRegistryError("minimum_age must be an integer or null")
    if entry.get("maximum_age") is not None and type(entry["maximum_age"]) is not int:
        raise PolicyRegistryError("maximum_age must be an integer or null")
    for key in ("allowed_locations", "allowed_occasions", "allowed_climates", "required_context"):
        if not isinstance(entry.get(key), list) or any(not isinstance(x, str) for x in entry[key]):
            raise PolicyRegistryError(f"{key} must be an array of strings")
    return {"policy_id": policy_id, **entry}
