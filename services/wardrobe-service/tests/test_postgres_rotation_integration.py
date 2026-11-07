from __future__ import annotations

import os
import subprocess
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.types.json import Json, Jsonb
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import main
from app.rotation import WardrobeRotationStateRow
from app.store import Base, WardrobeRow, engine_for_url


POSTGRES_DSN = os.getenv("WARDROBE_TEST_POSTGRES_DSN", "").strip()
pytestmark = pytest.mark.skipif(not POSTGRES_DSN, reason="WARDROBE_TEST_POSTGRES_DSN is not configured")


@pytest.fixture(scope="module", autouse=True)
def apply_postgres_migrations():
    migration_dir = Path(__file__).resolve().parents[1] / "migrations"
    for name in (
        "0001_initial.sql",
        "0002_wardrobe_learning_events.sql",
        "0003_saved_outfits.sql",
        "0004_rotation_state.sql",
        "0005_verified_purchase_ownership.sql",
        "0006_outfit_wear_history.sql",
        "0005_verified_purchase_ownership.sql",
        "0006_outfit_wear_history.sql",
    ):
        subprocess.run(
            ["psql", POSTGRES_DSN, "-v", "ON_ERROR_STOP=1", "-f", str(migration_dir / name)],
            check=True,
            capture_output=True,
            text=True,
        )


def _sqlalchemy_url() -> str:
    return POSTGRES_DSN.replace("postgresql://", "postgresql+psycopg://", 1)


def _database_dsn(database_name: str) -> str:
    options = conninfo_to_dict(POSTGRES_DSN)
    options["dbname"] = database_name
    return make_conninfo(**options)


def test_postgres_migrations_are_idempotent_and_custom_dump_restores_rotation_state():
    # Reapplying ordered, idempotent migrations must not damage an existing schema.
    migration_dir = Path(__file__).resolve().parents[1] / "migrations"
    for name in (
        "0001_initial.sql",
        "0002_wardrobe_learning_events.sql",
        "0003_saved_outfits.sql",
        "0004_rotation_state.sql",
        "0005_verified_purchase_ownership.sql",
        "0006_outfit_wear_history.sql",
    ):
        subprocess.run(
            ["psql", POSTGRES_DSN, "-v", "ON_ERROR_STOP=1", "-f", str(migration_dir / name)],
            check=True,
            capture_output=True,
            text=True,
        )

    owner = f"backup-owner-{uuid.uuid4().hex[:12]}"
    item_id = f"backup-item-{uuid.uuid4().hex[:12]}"
    request_id = f"backup-request-{uuid.uuid4().hex[:12]}"
    with psycopg.connect(POSTGRES_DSN) as conn:
        conn.execute(
            """
            INSERT INTO wardrobe_items
                (owner_user_id, item_id, display_name, category, attributes, status, version,
                 commerce_order_id, commerce_order_item_id, purchase_event_id,
                 purchase_quantity, purchase_currency, purchase_unit_price_minor, purchase_paid_at)
            VALUES (%s, %s, %s, %s, %s, 'active', 1, %s, %s, %s, 1, 'KES', 120000, '2026-11-07T08:00:00Z')
            """,
            (
                owner, item_id, "Backup linen shirt", "tops", Json(["linen", "blue"]),
                str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4()),
            ),
        )
        conn.execute(
            """
            INSERT INTO wardrobe_outfit_wear_events
                (owner_user_id, event_id, outfit_id, outfit_version, items_snapshot,
                 context, consent_receipt_id, payload_hash, delivery_result, observed_at)
            VALUES (%s, %s, %s, 1, %s, %s, %s, %s, %s, TIMESTAMPTZ '2026-11-07 08:30:00+00')
            """,
            (
                owner, f"wear-{uuid.uuid4().hex[:16]}", f"outfit-{uuid.uuid4().hex[:16]}",
                Jsonb([{"item_id": item_id, "item_version": 1}]), Jsonb({"occasion": "work"}),
                "receipt-restore-001", "c" * 64, Jsonb([{"item_id": item_id, "status": "recorded"}]),
            ),
        )
        conn.execute(
            """
            INSERT INTO wardrobe_rotation_states
                (owner_user_id, cycle_number, cycle_started_at, surfaced_item_ids,
                 version, last_request_id, last_request_hash)
            VALUES (%s, 3, TIMESTAMPTZ '2026-11-07 00:00:00+00',
                    %s, 9, %s, %s)
            """,
            (owner, Jsonb([item_id]), request_id, "a" * 64),
        )

    backup_db = f"wardrobe_restore_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(POSTGRES_DSN, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(backup_db)))
    restore_dsn = _database_dsn(backup_db)
    try:
        with tempfile.TemporaryDirectory(prefix="cirvanna-wardrobe-pg-") as temp_dir:
            backup_file = str(Path(temp_dir) / "wardrobe.dump")
            subprocess.run(
                ["pg_dump", "--format=custom", "--no-owner", "--no-privileges",
                 "--dbname", POSTGRES_DSN, "--file", backup_file],
                check=True, capture_output=True, text=True,
            )
            subprocess.run(
                ["pg_restore", "--no-owner", "--no-privileges", "--dbname", restore_dsn, backup_file],
                check=True, capture_output=True, text=True,
            )
        with psycopg.connect(restore_dsn) as restored:
            tables = {
                row[0] for row in restored.execute(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                ).fetchall()
            }
            assert "wardrobe_rotation_states" in tables
            assert "wardrobe_outfit_wear_events" in tables
            item_columns = {
                row[0] for row in restored.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = 'wardrobe_items'"
                ).fetchall()
            }
            assert {
                "commerce_order_id", "commerce_order_item_id", "purchase_event_id",
                "purchase_quantity", "purchase_currency", "purchase_unit_price_minor", "purchase_paid_at",
            }.issubset(item_columns)
            wear = restored.execute(
                "SELECT items_snapshot, context, consent_receipt_id FROM wardrobe_outfit_wear_events WHERE owner_user_id = %s",
                (owner,),
            ).fetchone()
            assert wear[0] == [{"item_id": item_id, "item_version": 1}]
            assert wear[1] == {"occasion": "work"}
            assert wear[2] == "receipt-restore-001"
            row = restored.execute(
                """
                SELECT cycle_number, surfaced_item_ids, version, last_request_id, last_request_hash
                FROM wardrobe_rotation_states WHERE owner_user_id = %s
                """,
                (owner,),
            ).fetchone()
            assert row == (3, [item_id], 9, request_id, "a" * 64)
            item = restored.execute(
                "SELECT display_name, attributes FROM wardrobe_items WHERE owner_user_id = %s AND item_id = %s",
                (owner, item_id),
            ).fetchone()
            assert item == ("Backup linen shirt", ["linen", "blue"])
    finally:
        with psycopg.connect(POSTGRES_DSN, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(backup_db)))


def test_postgres_compare_and_swap_serializes_concurrent_rotation_updates(monkeypatch):
    engine = engine_for_url(_sqlalchemy_url())
    Base.metadata.create_all(engine)
    owner = f"rotation-race-{uuid.uuid4().hex[:12]}"
    with Session(engine) as session, session.begin():
        session.add_all([
            WardrobeRow(
                owner_user_id=owner, item_id="top-a", display_name="Top A",
                category="tops", attributes=["linen"], status="active", version=1,
            ),
            WardrobeRow(
                owner_user_id=owner, item_id="bottom-a", display_name="Bottom A",
                category="trousers", attributes=["cotton"], status="active", version=1,
            ),
        ])
        session.add(WardrobeRotationStateRow(
            owner_user_id=owner, cycle_number=1,
            cycle_started_at=__import__("datetime").datetime.fromisoformat("2026-11-07T00:00:00+00:00"),
            surfaced_item_ids=["top-a"], version=1,
            last_request_id="seed-request-0001", last_request_hash="b" * 64,
            created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            updated_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        ))

    monkeypatch.setenv("WARDROBE_DATABASE_URL", _sqlalchemy_url())
    monkeypatch.setenv("WARDROBE_SERVICE_TOKEN", "postgres-rotation-test-token-more-than-32-bytes")
    headers = {"Authorization": "Bearer postgres-rotation-test-token-more-than-32-bytes"}
    bodies = [
        {
            "owner_user_id": owner, "request_id": f"race-request-{index:04d}",
            "expected_version": 1, "cycle_number": 1,
            "cycle_started_at": "2026-11-07T00:00:00Z",
            "surfaced_item_ids": ["top-a", "bottom-a"] if index == 1 else ["top-a"],
        }
        for index in (1, 2)
    ]

    def put(body):
        with TestClient(main.app) as client:
            response = client.put("/v1/rotation-state", headers=headers, json=body)
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(put, bodies))
    assert sorted(status for status, _ in outcomes) == [200, 409]
    conflict = next(body for status, body in outcomes if status == 409)
    assert conflict["detail"]["code"] == "WARDROBE_ROTATION_VERSION_CONFLICT"

    with Session(engine) as session:
        persisted = session.get(WardrobeRotationStateRow, owner)
        assert persisted is not None
        assert persisted.version == 2
        assert persisted.surfaced_item_ids in (["top-a"], ["top-a", "bottom-a"])
