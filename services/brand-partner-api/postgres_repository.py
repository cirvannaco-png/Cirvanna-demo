"""PostgreSQL implementation for brand accounts and atomic refresh-session rotation.

The caller must provide an asyncpg-compatible pool connected to an approved database.
This adapter is not wired into HTTP routes until migrations and deployment config are reviewed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

try:
    from .repository_contract import BrandAccount, BrandAccountStatus
except ImportError:
    from repository_contract import BrandAccount, BrandAccountStatus


class PostgresBrandRepository:
    def __init__(self, pool: Any):
        self._pool = pool

    @classmethod
    async def from_dsn(cls, dsn: str):
        if not dsn or not dsn.strip():
            raise RuntimeError("DATABASE_URL must be configured")
        try:
            import asyncpg
        except ImportError as exc:
            raise RuntimeError("Install the brand-partner-api requirements before using PostgreSQL") from exc
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5, command_timeout=10)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def _account(self, connection: Any, where_sql: str, value: str, *, lock: bool = False):
        suffix = " FOR UPDATE" if lock else ""
        row = await connection.fetchrow(
            f"""SELECT brand_id::text AS brand_id, email_normalized, brand_name, password_hash,
                       status, created_at, updated_at
                FROM brand_accounts WHERE {where_sql}{suffix}""",
            value,
        )
        if row is None:
            return None
        permissions = await connection.fetch(
            "SELECT permission FROM brand_account_permissions WHERE brand_id = $1::uuid ORDER BY permission",
            row["brand_id"],
        )
        return BrandAccount(
            brand_id=row["brand_id"], email_normalized=row["email_normalized"],
            brand_name=row["brand_name"], password_hash=row["password_hash"],
            status=BrandAccountStatus(row["status"]),
            permissions=tuple(item["permission"] for item in permissions),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    async def get_by_normalized_email(self, email: str) -> BrandAccount | None:
        async with self._pool.acquire() as connection:
            return await self._account(connection, "email_normalized = $1", email)

    async def get_by_id(self, brand_id: str) -> BrandAccount | None:
        async with self._pool.acquire() as connection:
            return await self._account(connection, "brand_id = $1::uuid", brand_id)

    async def create_pending(self, *, email_normalized: str, brand_name: str, password_hash: str) -> BrandAccount:
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """INSERT INTO brand_accounts (email_normalized, brand_name, password_hash, status)
                       VALUES ($1, $2, $3, 'pending')
                       RETURNING brand_id::text AS brand_id, email_normalized, brand_name, password_hash,
                                 status, created_at, updated_at""",
                    email_normalized, brand_name, password_hash,
                )
                await connection.execute(
                    """INSERT INTO brand_auth_audit_events
                       (actor_id, brand_id, event_type, outcome, metadata)
                       VALUES ('system:registration', $1::uuid, 'brand_registration', 'success', '{}'::jsonb)""",
                    row["brand_id"],
                )
                return BrandAccount(
                    brand_id=row["brand_id"], email_normalized=row["email_normalized"],
                    brand_name=row["brand_name"], password_hash=row["password_hash"],
                    status=BrandAccountStatus(row["status"]), permissions=(),
                    created_at=row["created_at"], updated_at=row["updated_at"],
                )

    async def update_status(self, *, brand_id: str, status: BrandAccountStatus, actor_id: str) -> BrandAccount:
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                current = await self._account(connection, "brand_id = $1::uuid", brand_id, lock=True)
                if current is None:
                    raise ValueError("Brand account not found")
                if current.status is BrandAccountStatus.DELETED and status is not BrandAccountStatus.DELETED:
                    raise ValueError("Deleted accounts cannot be reactivated")
                if current.status is BrandAccountStatus.PENDING and status is BrandAccountStatus.SUSPENDED:
                    raise ValueError("Pending accounts must be reviewed before suspension")
                now = datetime.now(timezone.utc)
                row = await connection.fetchrow(
                    """UPDATE brand_accounts
                       SET status = $2, updated_at = $3,
                           approved_at = CASE WHEN $2 = 'active' AND approved_at IS NULL THEN $3 ELSE approved_at END,
                           approved_by = CASE WHEN $2 = 'active' AND approved_by IS NULL THEN $4 ELSE approved_by END,
                           deleted_at = CASE WHEN $2 = 'deleted' THEN $3 ELSE deleted_at END
                       WHERE brand_id = $1::uuid
                       RETURNING brand_id::text AS brand_id, email_normalized, brand_name, password_hash,
                                 status, created_at, updated_at""",
                    brand_id, status.value, now, actor_id,
                )
                await connection.execute(
                    """INSERT INTO brand_auth_audit_events
                       (actor_id, brand_id, event_type, outcome, metadata)
                       VALUES ($1, $2::uuid, 'brand_status_change', 'success',
                               jsonb_build_object('from', $3, 'to', $4))""",
                    actor_id, brand_id, current.status.value, status.value,
                )
                return BrandAccount(
                    brand_id=row["brand_id"], email_normalized=row["email_normalized"],
                    brand_name=row["brand_name"], password_hash=row["password_hash"],
                    status=BrandAccountStatus(row["status"]), permissions=current.permissions,
                    created_at=row["created_at"], updated_at=row["updated_at"],
                )

    async def replace_permissions(self, *, brand_id: str, permissions: tuple[str, ...], actor_id: str) -> BrandAccount:
        normalized = tuple(sorted(set(permissions)))
        if any(not isinstance(p, str) or not p or len(p) > 128 for p in normalized):
            raise ValueError("Invalid permission value")
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                current = await self._account(connection, "brand_id = $1::uuid", brand_id, lock=True)
                if current is None:
                    raise ValueError("Brand account not found")
                if current.status in {BrandAccountStatus.SUSPENDED, BrandAccountStatus.DELETED}:
                    raise ValueError("Cannot change permissions for inactive account")
                await connection.execute("DELETE FROM brand_account_permissions WHERE brand_id = $1::uuid", brand_id)
                for permission in normalized:
                    await connection.execute(
                        """INSERT INTO brand_account_permissions (brand_id, permission, granted_by)
                           VALUES ($1::uuid, $2, $3)""",
                        brand_id, permission, actor_id,
                    )
                await connection.execute(
                    """INSERT INTO brand_auth_audit_events
                       (actor_id, brand_id, event_type, outcome, metadata)
                       VALUES ($1, $2::uuid, 'brand_permissions_replace', 'success',
                               jsonb_build_object('permissions', $3::text[]))""",
                    actor_id, brand_id, list(normalized),
                )
                return BrandAccount(
                    brand_id=current.brand_id, email_normalized=current.email_normalized,
                    brand_name=current.brand_name, password_hash=current.password_hash,
                    status=current.status, permissions=normalized,
                    created_at=current.created_at, updated_at=current.updated_at,
                )

    async def consume_and_rotate(
        self, *, token_id: str, brand_id: str, presented_token_hash: str,
        replacement_token_id: str, replacement_token_hash: str, expires_at: datetime,
    ) -> bool:
        """Atomically consume one refresh session and insert its replacement."""
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                current = await connection.fetchrow(
                    """SELECT token_hash, expires_at, consumed_at, revoked_at
                       FROM brand_refresh_sessions
                       WHERE token_id = $1::uuid AND brand_id = $2::uuid
                       FOR UPDATE""",
                    token_id, brand_id,
                )
                now = datetime.now(timezone.utc)
                if (current is None or current["token_hash"] != presented_token_hash
                    or current["expires_at"] <= now or current["consumed_at"] is not None
                    or current["revoked_at"] is not None or expires_at <= now):
                    return False
                active = await connection.fetchval(
                    "SELECT status = 'active' FROM brand_accounts WHERE brand_id = $1::uuid FOR UPDATE",
                    brand_id,
                )
                if active is not True:
                    return False
                await connection.execute(
                    """UPDATE brand_refresh_sessions
                       SET consumed_at = $2, replaced_by = $3::uuid
                       WHERE token_id = $1::uuid""",
                    token_id, now, replacement_token_id,
                )
                await connection.execute(
                    """INSERT INTO brand_refresh_sessions
                       (token_id, brand_id, token_hash, expires_at)
                       VALUES ($1::uuid, $2::uuid, $3, $4)""",
                    replacement_token_id, brand_id, replacement_token_hash, expires_at,
                )
                await connection.execute(
                    """INSERT INTO brand_auth_audit_events
                       (actor_id, brand_id, event_type, outcome, metadata)
                       VALUES ('system:refresh', $1::uuid, 'refresh_token_rotation', 'success', '{}'::jsonb)""",
                    brand_id,
                )
                return True

    async def revoke_all_for_brand(self, *, brand_id: str, actor_id: str) -> int:
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                result = await connection.execute(
                    """UPDATE brand_refresh_sessions SET revoked_at = now()
                       WHERE brand_id = $1::uuid AND consumed_at IS NULL AND revoked_at IS NULL""",
                    brand_id,
                )
                count = int(result.rsplit(" ", 1)[-1])
                await connection.execute(
                    """INSERT INTO brand_auth_audit_events
                       (actor_id, brand_id, event_type, outcome, metadata)
                       VALUES ($1, $2::uuid, 'refresh_sessions_revoked', 'success',
                               jsonb_build_object('count', $3::int))""",
                    actor_id, brand_id, count,
                )
                return count
