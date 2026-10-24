"""Real PostgreSQL integration test for the brand persistence adapter.

Runs only when TEST_DATABASE_URL points to a disposable test database.
"""
import asyncio
import hashlib
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is not configured; PostgreSQL integration test skipped",
)


def test_postgres_account_and_refresh_session_lifecycle():
    import asyncpg
    async def exercise():
        dsn = os.environ["TEST_DATABASE_URL"]
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=3)
        try:
            schema = (Path(__file__).resolve().parents[1] / "services" / "brand-partner-api" / "schema.sql").read_text()
            async with pool.acquire() as connection:
                await connection.execute(schema)
                await connection.execute(
                    "TRUNCATE brand_auth_audit_events, brand_refresh_sessions, brand_account_permissions, brand_accounts CASCADE"
                )

            repository = load_repository(pool)
            account = await repository.create_pending(
                email_normalized="integration@example.com",
                brand_name="Integration Brand",
                password_hash="test-only-scrypt-hash",
            )
            assert account.status.value == "pending"
            account = await repository.update_status(
                brand_id=account.brand_id, status=__import__("repository_contract").BrandAccountStatus.ACTIVE,
                actor_id="integration-reviewer",
            )
            assert account.status.value == "active"

            account = await repository.replace_permissions(
                brand_id=account.brand_id, permissions=("products:read", "analytics:read"),
                actor_id="integration-reviewer",
            )
            fetched = await repository.get_by_normalized_email("integration@example.com")
            assert fetched is not None
            assert fetched.permissions == ("analytics:read", "products:read")

            now = datetime.now(timezone.utc)
            token_id, replacement_id = str(uuid4()), str(uuid4())
            presented_hash = hashlib.sha256(b"test-refresh-token").hexdigest()
            replacement_hash = hashlib.sha256(b"test-replacement-token").hexdigest()
            await repository.create_refresh_session(
                token_id=token_id, brand_id=account.brand_id, token_hash=presented_hash,
                expires_at=now + timedelta(days=2),
            )
            rotated = await repository.consume_and_rotate(
                token_id=token_id, brand_id=account.brand_id, presented_token_hash=presented_hash,
                replacement_token_id=replacement_id, replacement_token_hash=replacement_hash,
                expires_at=now + timedelta(days=30),
            )
            assert rotated is True
            replayed = await repository.consume_and_rotate(
                token_id=token_id, brand_id=account.brand_id, presented_token_hash=presented_hash,
                replacement_token_id=str(uuid4()), replacement_token_hash=hashlib.sha256(b"another").hexdigest(),
                expires_at=now + timedelta(days=30),
            )
            assert replayed is False
            assert await repository.revoke_all_for_brand(
                brand_id=account.brand_id, actor_id="integration-reviewer",
            ) == 1
            events = await pool.fetchval(
                "SELECT count(*) FROM brand_auth_audit_events WHERE brand_id = $1::uuid",
                account.brand_id,
            )
            assert events >= 4
        finally:
            await pool.close()

    asyncio.run(exercise())


def load_repository(pool):
    from pathlib import Path
    import importlib.util
    import sys
    service = Path(__file__).resolve().parents[1] / "services" / "brand-partner-api"
    sys.path.insert(0, str(service))
    spec = importlib.util.spec_from_file_location("repository_contract", service / "repository_contract.py")
    contract = importlib.util.module_from_spec(spec)
    sys.modules["repository_contract"] = contract
    spec.loader.exec_module(contract)
    spec2 = importlib.util.spec_from_file_location("postgres_repository", service / "postgres_repository.py")
    module = importlib.util.module_from_spec(spec2)
    sys.modules["postgres_repository"] = module
    spec2.loader.exec_module(module)
    return module.PostgresBrandRepository(pool)
