"""Persistence contract for brand accounts; no fake or in-memory production store."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol


class BrandAccountStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"


@dataclass(frozen=True)
class BrandAccount:
    brand_id: str
    email_normalized: str
    brand_name: str
    password_hash: str
    status: BrandAccountStatus
    permissions: tuple[str, ...]
    created_at: datetime
    updated_at: datetime


class BrandAccountRepository(Protocol):
    """Implement against Cirvanna's canonical persistence adapter before route enablement."""

    async def get_by_normalized_email(self, email: str) -> BrandAccount | None: ...
    async def get_by_id(self, brand_id: str) -> BrandAccount | None: ...
    async def create_pending(self, *, email_normalized: str, brand_name: str, password_hash: str) -> BrandAccount: ...
    async def update_status(self, *, brand_id: str, status: BrandAccountStatus, actor_id: str) -> BrandAccount: ...
    async def replace_permissions(self, *, brand_id: str, permissions: tuple[str, ...], actor_id: str) -> BrandAccount: ...


class RefreshTokenRepository(Protocol):
    """Server-side storage must hash token identifiers and support atomic rotation/revocation."""

    async def consume_and_rotate(
        self, *, token_id: str, brand_id: str, presented_token_hash: str,
        replacement_token_id: str, replacement_token_hash: str, expires_at: datetime
    ) -> bool: ...
    async def revoke_all_for_brand(self, *, brand_id: str, actor_id: str) -> int: ...
