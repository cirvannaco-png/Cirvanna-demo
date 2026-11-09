#!/usr/bin/env python3
"""Validate Cirvanna's provider-neutral canonical deployment inventory."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "infrastructure" / "deployment" / "canonical-stack.json"
EXPOSURES = {"public_edge", "private_api", "private_worker", "not_containerized"}


def validate_manifest(document: dict[str, Any], root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    if document.get("schema_version") != 1:
        errors.append("schema_version must equal 1")
    if document.get("repository") != "cirvannaco-png/Cirvanna-demo":
        errors.append("repository identity mismatch")
    if document.get("artifact_kind") != "provider_neutral_system_deployment_inventory":
        errors.append("artifact_kind mismatch")
    if document.get("release_status") != "blocked":
        errors.append("release_status must remain blocked until production evidence exists")
    deployment = document.get("deployment")
    if not isinstance(deployment, dict) or deployment.get("operationally_complete") is not False:
        errors.append("deployment.operationally_complete must remain false until independently verified")

    services = document.get("services")
    providers = document.get("external_providers")
    stores = document.get("data_stores")
    if not isinstance(services, list) or not services:
        return errors + ["services must be a non-empty array"]
    if not isinstance(providers, list) or not isinstance(stores, list):
        return errors + ["external_providers and data_stores must be arrays"]

    ids: list[str] = []
    service_by_id: dict[str, dict[str, Any]] = {}
    for item in services:
        if not isinstance(item, dict):
            errors.append("every service entry must be an object")
            continue
        service_id = item.get("id")
        if not isinstance(service_id, str) or not service_id.strip():
            errors.append("each service must have a non-empty id")
            continue
        ids.append(service_id)
        service_by_id[service_id] = item
        if not isinstance(item.get("source_path"), str) or not (root / item["source_path"]).is_dir():
            errors.append(f"{service_id}: source_path must exist and be a directory")
        if item.get("exposure") not in EXPOSURES:
            errors.append(f"{service_id}: invalid exposure")
        if item.get("production_enabled") is not False:
            errors.append(f"{service_id}: production_enabled must remain false in the unprovisioned inventory")
        if not isinstance(item.get("required_for_marketplace"), bool):
            errors.append(f"{service_id}: required_for_marketplace must be boolean")
        if not isinstance(item.get("depends_on_services"), list):
            errors.append(f"{service_id}: depends_on_services must be an array")
        if not isinstance(item.get("depends_on_providers"), list):
            errors.append(f"{service_id}: depends_on_providers must be an array")
        if item.get("containerized") is True:
            dockerfile = item.get("dockerfile")
            context = item.get("build_context")
            if not isinstance(dockerfile, str) or not (root / dockerfile).is_file():
                errors.append(f"{service_id}: declared Dockerfile does not exist")
            if not isinstance(context, str) or not (root / context).is_dir():
                errors.append(f"{service_id}: build_context must exist and be a directory")
        elif item.get("containerized") is False:
            if item.get("dockerfile") is not None or item.get("build_context") is not None:
                errors.append(f"{service_id}: non-containerized services must not declare a Dockerfile or build context")
            if item.get("exposure") != "not_containerized":
                errors.append(f"{service_id}: non-containerized service must use not_containerized exposure")
        else:
            errors.append(f"{service_id}: containerized must be boolean")

    if len(ids) != len(set(ids)):
        errors.append("service ids must be unique")
    public_edges = [item.get("id") for item in services if item.get("exposure") == "public_edge"]
    if public_edges != ["marketplace-bff"]:
        errors.append("marketplace-bff must be the sole public browser ingress")
    if document.get("public_ingress") != "marketplace-bff":
        errors.append("public_ingress must name marketplace-bff")

    provider_ids: list[str] = []
    for provider in providers:
        if not isinstance(provider, dict):
            errors.append("every provider entry must be an object")
            continue
        provider_id = provider.get("id")
        if not isinstance(provider_id, str) or not provider_id.strip():
            errors.append("each provider must have a non-empty id")
            continue
        provider_ids.append(provider_id)
        if provider.get("configured_for_production") is not False:
            errors.append(f"{provider_id}: production provider configuration must remain unverified")
        if provider.get("operationally_verified") is not False:
            errors.append(f"{provider_id}: operational verification must remain false until proven")
        if not isinstance(provider.get("release_gate"), str) or not provider["release_gate"].startswith("REL-"):
            errors.append(f"{provider_id}: release_gate is required")
    if len(provider_ids) != len(set(provider_ids)):
        errors.append("provider ids must be unique")

    provider_set = set(provider_ids)
    service_set = set(ids)
    for service_id, item in service_by_id.items():
        for dependency in item.get("depends_on_services", []):
            if dependency not in service_set:
                errors.append(f"{service_id}: unknown service dependency {dependency!r}")
        for dependency in item.get("depends_on_providers", []):
            if dependency not in provider_set:
                errors.append(f"{service_id}: unknown provider dependency {dependency!r}")

    store_ids: list[str] = []
    for store in stores:
        if not isinstance(store, dict):
            errors.append("every data store entry must be an object")
            continue
        store_id = store.get("id")
        if not isinstance(store_id, str) or not store_id.strip():
            errors.append("each data store must have a non-empty id")
            continue
        store_ids.append(store_id)
        if store.get("owner_service") not in service_set:
            errors.append(f"{store_id}: owner_service must reference a declared service")
        if store.get("provisioned_for_production") is not False:
            errors.append(f"{store_id}: production provisioning is not verified")
        if store.get("backup_restore_verified") is not False:
            errors.append(f"{store_id}: backup/restore verification is not recorded")
    if len(store_ids) != len(set(store_ids)):
        errors.append("data store ids must be unique")
    store_set = set(store_ids)
    for service_id, item in service_by_id.items():
        for store_ref in item.get("data_store_refs", []):
            if store_ref not in store_set:
                errors.append(f"{service_id}: unknown data store reference {store_ref!r}")

    # Validate service dependency cycles so deployment ordering is deterministic.
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(service_id: str) -> None:
        if service_id in visiting:
            errors.append(f"service dependency cycle includes {service_id}")
            return
        if service_id in visited:
            return
        visiting.add(service_id)
        for dependency in service_by_id.get(service_id, {}).get("depends_on_services", []):
            if dependency in service_by_id:
                visit(dependency)
        visiting.remove(service_id)
        visited.add(service_id)

    for service_id in service_by_id:
        visit(service_id)
    return errors


def main() -> int:
    try:
        document = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot load canonical deployment inventory: {exc}")
        return 1
    errors = validate_manifest(document)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(
        f"OK: {len(document['services'])} service entries, "
        f"{len(document['data_stores'])} data stores, and "
        f"{len(document['external_providers'])} external providers inventoried. "
        "Deployment remains blocked and unprovisioned."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
