"""Server-authoritative, version-pinned EEPL policy resolver shared by services."""
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


def _registry() -> dict[str, dict[str, Any]]:
    raw = os.getenv("EEPL_POLICY_REGISTRY_JSON", "").strip()
    if not raw:
        raise PolicyRegistryError("server policy registry is not configured")
    try:
        registry = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PolicyRegistryError("server policy registry is invalid JSON") from exc
    if not isinstance(registry, dict) or not registry:
        raise PolicyRegistryError("server policy registry must be a non-empty object")
    return registry


def resolve_policy(policy_id: str, policy_version: str) -> dict[str, Any]:
    """Resolve a specific registered policy; callers must not select the active one."""
    if not isinstance(policy_id, str) or not policy_id.strip():
        raise PolicyRegistryError("policy ID must be a non-empty string")
    if not isinstance(policy_version, str) or not policy_version.strip():
        raise PolicyRegistryError("policy version must be a non-empty string")
    registry = _registry()
    entry = registry.get(policy_id)
    if not isinstance(entry, dict) or set(entry) != _REQUIRED:
        raise PolicyRegistryError("policy is not registered on this server")
    if entry.get("policy_version") != policy_version:
        raise PolicyRegistryError("policy version is not the active server version")
    if entry.get("minimum_age") is not None and type(entry["minimum_age"]) is not int:
        raise PolicyRegistryError("minimum_age must be an integer or null")
    if entry.get("maximum_age") is not None and type(entry["maximum_age"]) is not int:
        raise PolicyRegistryError("maximum_age must be an integer or null")
    if entry.get("minimum_age") is not None and not 0 <= entry["minimum_age"] <= 125:
        raise PolicyRegistryError("minimum_age is outside supported bounds")
    if entry.get("maximum_age") is not None and not 0 <= entry["maximum_age"] <= 125:
        raise PolicyRegistryError("maximum_age is outside supported bounds")
    if entry.get("minimum_age") is not None and entry.get("maximum_age") is not None and entry["maximum_age"] < entry["minimum_age"]:
        raise PolicyRegistryError("maximum_age cannot be below minimum_age")
    for key in ("allowed_locations", "allowed_occasions", "allowed_climates", "required_context"):
        if not isinstance(entry.get(key), list) or any(not isinstance(x, str) for x in entry[key]):
            raise PolicyRegistryError(f"{key} must be an array of strings")
    return {"policy_id": policy_id, **entry}


def resolve_active_policy() -> dict[str, Any]:
    """Resolve only the policy selected by trusted server-side configuration."""
    policy_id = os.getenv("EEPL_POLICY_ID", "").strip()
    if not policy_id:
        raise PolicyRegistryError("active server policy ID is not configured")
    registry = _registry()
    entry = registry.get(policy_id)
    if not isinstance(entry, dict):
        raise PolicyRegistryError("active server policy ID is not registered")
    version = entry.get("policy_version")
    if not isinstance(version, str) or not version.strip():
        raise PolicyRegistryError("active server policy version is invalid")
    return resolve_policy(policy_id, version)
