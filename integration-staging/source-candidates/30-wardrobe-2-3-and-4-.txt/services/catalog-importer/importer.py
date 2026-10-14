"""Standalone CLI to batch-import garment catalogs (CSV or JSON)."""
from __future__ import annotations

import asyncio
import csv
import json
import logging
import sys
from pathlib import Path
from typing import Any

import click
import httpx

from common.domain import ColorVector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("catalog-importer")


def _row_to_item(row: dict[str, str]) -> dict[str, Any]:
    category = row.get("category", "top").strip().lower()
    try:
        color = ColorVector.from_hex(row.get("color", "#808080")).to_dict()
    except Exception:
        color = {"l": 50.0, "a": 0.0, "b": 0.0}

    return {
        "owner_id": row.get("owner_id", "system"),
        "ingestion_method": "catalog_import",
        "primary_category": category,
        "bootstrap_confidence": 0.1,
        "geometry_data": {
            "silhouette_class": row.get("silhouette", "relaxed").strip().lower(),
            "length_profile": row.get("length", "hip").strip(),
            "volume_distribution": [0.33, 0.34, 0.33],
            "stretch_behavior": row.get("stretch", "semi_flexible").strip(),
        },
        "surface_data": {
            "dominant_color": color,
            "color_variance": 0.5,
            "texture_class": row.get("texture", "smooth").strip().lower(),
            "pattern_density": 0.0,
            "lighting_risk": 0.5,
        },
        "catalog_metadata": dict(row),
    }


async def _send_batch(
    client: httpx.AsyncClient, url: str, batch: list[dict], token: str
) -> int:
    headers = {"Authorization": f"Bearer {token}"}
    ok = 0
    for item in batch:
        try:
            r = await client.post(f"{url}/items", json=item, headers=headers, timeout=30.0)
            r.raise_for_status()
            ok += 1
        except httpx.HTTPError as exc:
            log.error(f"Failed to import item: {exc}")
    return ok


async def _import_csv(url: str, path: Path, chunk: int, token: str) -> tuple[int, int]:
    total = ok = 0
    async with httpx.AsyncClient() as client:
        with path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            batch: list[dict] = []
            for row in reader:
                total += 1
                batch.append(_row_to_item(row))
                if len(batch) >= chunk:
                    ok += await _send_batch(client, url, batch, token)
                    batch = []
                    log.info(f"Progress: {total} rows processed")
            if batch:
                ok += await _send_batch(client, url, batch, token)
    return total, ok


async def _import_json(url: str, path: Path, chunk: int, token: str) -> tuple[int, int]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    rows = data if isinstance(data, list) else data.get("items", [])
    total = len(rows)
    ok = 0
    async with httpx.AsyncClient() as client:
        for i in range(0, total, chunk):
            batch = [_row_to_item(r) for r in rows[i : i + chunk]]
            ok += await _send_batch(client, url, batch, token)
            log.info(f"Progress: {min(i + chunk, total)}/{total}")
    return total, ok


@click.command()
@click.option("--file", "file_path", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--url", default="http://localhost:8080", help="API gateway base URL")
@click.option("--chunk", default=100, type=int, help="Batch size")
@click.option("--token", required=True, help="JWT bearer token")
def cli(file_path: Path, url: str, chunk: int, token: str) -> None:
    """Import a catalog from CSV or JSON."""
    if file_path.suffix.lower() == ".csv":
        coro = _import_csv(url, file_path, chunk, token)
    elif file_path.suffix.lower() == ".json":
        coro = _import_json(url, file_path, chunk, token)
    else:
        click.echo(f"Unsupported file type: {file_path.suffix}", err=True)
        sys.exit(1)

    total, ok = asyncio.run(coro)
    click.echo(f"Imported {ok}/{total} items successfully")
    if ok != total:
        sys.exit(1)


if __name__ == "__main__":
    cli()
