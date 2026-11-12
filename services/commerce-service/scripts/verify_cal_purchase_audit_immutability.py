"""Verify that the migrated CAL purchase audit table rejects mutation.

Run only against a disposable migration-test database. The inserted fixture row is
intentionally retained because an immutable audit row must not be deleted.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, delete, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.main import CALPurchaseAudit


def require_blocked(session: Session, statement, label: str) -> None:
    try:
        session.execute(statement)
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        return
    raise SystemExit(f"FAIL: database allowed CAL audit {label}")


def main() -> None:
    database_url = os.getenv("COMMERCE_DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("COMMERCE_DATABASE_URL is required")

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
        with Session(engine) as session:
            session.add(row)
            session.commit()

            require_blocked(
                session,
                update(CALPurchaseAudit)
                .where(CALPurchaseAudit.audit_id == audit_id)
                .values(reason_code="tampered"),
                "UPDATE",
            )
            require_blocked(
                session,
                delete(CALPurchaseAudit).where(CALPurchaseAudit.audit_id == audit_id),
                "DELETE",
            )

            retained = session.scalar(
                select(CALPurchaseAudit).where(CALPurchaseAudit.audit_id == audit_id)
            )
            if retained is None or retained.reason_code is not None:
                raise SystemExit("FAIL: CAL audit evidence was not retained unchanged")

        if engine.dialect.name == "postgresql":
            with engine.connect() as connection:
                try:
                    connection.execute(text("TRUNCATE TABLE commerce_cal_purchase_audits"))
                    connection.commit()
                except SQLAlchemyError:
                    connection.rollback()
                else:
                    raise SystemExit("FAIL: database allowed CAL audit TRUNCATE")

        print("PASS: CAL purchase audit UPDATE/DELETE are rejected by the database")
        if engine.dialect.name == "postgresql":
            print("PASS: CAL purchase audit TRUNCATE is rejected by the database")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
