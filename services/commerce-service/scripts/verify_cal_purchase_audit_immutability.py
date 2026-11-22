"""Verify CAL purchase audit immutability under non-owner runtime credentials.

Run only against a disposable migration-test database. PostgreSQL migrations must
run as the schema owner; application and probe credentials must be non-owner roles.
The inserted fixture row is intentionally retained as immutable audit evidence.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine, delete, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import CALPurchaseAudit  # noqa: E402


TABLE = "commerce_cal_purchase_audits"
ROW_TRIGGER = "trg_commerce_cal_purchase_audits_no_update_delete"
TRUNCATE_TRIGGER = "trg_commerce_cal_purchase_audits_no_truncate"


def sqlstate(exc: SQLAlchemyError) -> str | None:
    original = getattr(exc, "orig", None)
    return getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)


def require_blocked(session: Session, statement, label: str, *, expected_sqlstate: str | None = None) -> None:
    try:
        session.execute(statement)
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        if expected_sqlstate and sqlstate(exc) != expected_sqlstate:
            raise SystemExit(
                f"FAIL: CAL audit {label} was rejected for {sqlstate(exc)!r}, "
                f"expected trigger SQLSTATE {expected_sqlstate}"
            ) from exc
        return
    raise SystemExit(f"FAIL: database allowed CAL audit {label}")


def assert_postgres_runtime_is_not_owner(engine) -> None:
    with engine.connect() as connection:
        role = connection.execute(text(f"""
            SELECT current_user AS runtime_role,
                   pg_get_userbyid(c.relowner) AS table_owner,
                   r.rolsuper,
                   r.rolcreaterole,
                   r.rolcreatedb,
                   pg_has_role(current_user, c.relowner, 'MEMBER') AS owner_member,
                   has_table_privilege(current_user, c.oid, 'TRUNCATE') AS can_truncate,
                   has_schema_privilege(current_user, 'public', 'CREATE') AS can_create_in_public
            FROM pg_class c
            JOIN pg_roles r ON r.rolname = current_user
            WHERE c.oid = '{TABLE}'::regclass AND c.relkind = 'r'
        """)).mappings().one()
        if (
            role["runtime_role"] == role["table_owner"]
            or role["rolsuper"]
            or role["rolcreaterole"]
            or role["rolcreatedb"]
            or role["owner_member"]
            or role["can_truncate"]
            or role["can_create_in_public"]
        ):
            raise SystemExit(f"FAIL: Commerce runtime role is over-privileged: {dict(role)}")

        triggers = dict(connection.execute(text(f"""
            SELECT tgname, tgenabled
            FROM pg_trigger
            WHERE tgrelid = '{TABLE}'::regclass AND NOT tgisinternal
        """)).all())
        if triggers.get(ROW_TRIGGER) != "O" or triggers.get(TRUNCATE_TRIGGER) != "O":
            raise SystemExit(f"FAIL: CAL audit immutability triggers are missing or disabled: {triggers}")

        for statement, label in (
            (f"ALTER TABLE {TABLE} DISABLE TRIGGER {ROW_TRIGGER}", "disable-trigger"),
            (f"DROP TRIGGER {TRUNCATE_TRIGGER} ON {TABLE}", "drop-trigger"),
        ):
            try:
                connection.execute(text(statement))
                connection.commit()
            except SQLAlchemyError as exc:
                connection.rollback()
                if sqlstate(exc) != "42501":
                    raise SystemExit(
                        f"FAIL: runtime {label} was rejected for unexpected SQLSTATE {sqlstate(exc)!r}"
                    ) from exc
            else:
                raise SystemExit(f"FAIL: Commerce runtime role could {label}")


def assert_truncate_trigger_blocks_non_owner_probe(runtime_engine, audit_id: str) -> None:
    probe_url = os.getenv("COMMERCE_CAL_AUDIT_PROBE_DATABASE_URL", "").strip()
    if not probe_url:
        raise SystemExit("COMMERCE_CAL_AUDIT_PROBE_DATABASE_URL is required for PostgreSQL trigger verification")
    probe_engine = create_engine(probe_url, pool_pre_ping=True)
    try:
        with probe_engine.connect() as connection:
            role = connection.execute(text(f"""
                SELECT current_user AS probe_role,
                       pg_get_userbyid(c.relowner) AS table_owner,
                       r.rolsuper,
                       pg_has_role(current_user, c.relowner, 'MEMBER') AS owner_member,
                       has_table_privilege(current_user, c.oid, 'TRUNCATE') AS can_truncate
                FROM pg_class c
                JOIN pg_roles r ON r.rolname = current_user
                WHERE c.oid = '{TABLE}'::regclass AND c.relkind = 'r'
            """)).mappings().one()
            if (
                role["probe_role"] == role["table_owner"]
                or role["rolsuper"]
                or role["owner_member"]
                or not role["can_truncate"]
            ):
                raise SystemExit(f"FAIL: invalid non-owner TRUNCATE probe role: {dict(role)}")
            try:
                connection.execute(text(f"TRUNCATE TABLE {TABLE}"))
                connection.commit()
            except SQLAlchemyError as exc:
                connection.rollback()
                if sqlstate(exc) != "55000":
                    raise SystemExit(
                        f"FAIL: TRUNCATE was rejected for unexpected SQLSTATE {sqlstate(exc)!r}"
                    ) from exc
            else:
                raise SystemExit("FAIL: non-owner TRUNCATE probe bypassed the immutable audit trigger")
    finally:
        probe_engine.dispose()

    with Session(runtime_engine) as session:
        retained = session.scalar(
            select(CALPurchaseAudit).where(CALPurchaseAudit.audit_id == audit_id)
        )
        if retained is None:
            raise SystemExit("FAIL: CAL audit row disappeared after rejected TRUNCATE")


def main() -> None:
    database_url = os.getenv("COMMERCE_DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("COMMERCE_DATABASE_URL is required; it must identify the Commerce runtime role")

    engine = create_engine(database_url, pool_pre_ping=True)
    audit_id = str(uuid.uuid4())
    observed = datetime.now(timezone.utc)
    row = CALPurchaseAudit(
        audit_id=audit_id,
        order_id=None,
        cart_id=None,
        cart_version=None,
        buyer_user_id="migration-test:cal-audit-immutability",
        action="cart_view",
        catalog_product_id=str(uuid.uuid4()),
        candidate_id=str(uuid.uuid4()),
        variant_id=str(uuid.uuid4()),
        listing_id=str(uuid.uuid4()),
        merchant_id=str(uuid.uuid4()),
        offer_snapshot_sha256="a" * 64,
        market_country_code=None,
        destination_key_sha256=None,
        fulfillment_mode=None,
        display_currency=None,
        quantity=1,
        unit_price_minor=0,
        currency="KES",
        catalog_version=1,
        request_id="migration-test-cal-audit-immutability",
        policy_version="migration-test-only",
        decision="SHOW",
        reason_code=None,
        receipt={"test_fixture": True},
        issued_at=observed,
        expires_at=observed + timedelta(minutes=5),
        created_at=observed,
    )

    try:
        if engine.dialect.name == "postgresql":
            assert_postgres_runtime_is_not_owner(engine)

        with Session(engine) as session:
            session.add(row)
            session.commit()

            require_blocked(
                session,
                update(CALPurchaseAudit)
                .where(CALPurchaseAudit.audit_id == audit_id)
                .values(reason_code="tampered"),
                "UPDATE",
                expected_sqlstate="55000" if engine.dialect.name == "postgresql" else None,
            )
            require_blocked(
                session,
                delete(CALPurchaseAudit).where(CALPurchaseAudit.audit_id == audit_id),
                "DELETE",
                expected_sqlstate="55000" if engine.dialect.name == "postgresql" else None,
            )

            retained = session.scalar(
                select(CALPurchaseAudit).where(CALPurchaseAudit.audit_id == audit_id)
            )
            if retained is None or retained.reason_code is not None:
                raise SystemExit("FAIL: CAL audit evidence was not retained unchanged")

        if engine.dialect.name == "postgresql":
            assert_truncate_trigger_blocks_non_owner_probe(engine, audit_id)

        print("PASS: runtime role is not schema/table owner and cannot alter immutability guards")
        print("PASS: CAL purchase audit UPDATE/DELETE are rejected by database triggers")
        if engine.dialect.name == "postgresql":
            print("PASS: a separate non-owner role with TRUNCATE privilege is rejected by the database trigger")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
