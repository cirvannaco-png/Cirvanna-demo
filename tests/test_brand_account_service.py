"""Tests for brand account lifecycle rules with a test-only repository double."""
import asyncio
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "services" / "brand-partner-api"
sys.path.insert(0, str(SERVICE))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


contract = _load("repository_contract", SERVICE / "repository_contract.py")
token_security = _load("token_security", SERVICE / "token_security.py")
accounts = _load("account_service", SERVICE / "account_service.py")


class FakeRepository:
    """Test-only repository double; not used in production."""

    def __init__(self):
        self.accounts = {}
        self.next_id = 1

    async def get_by_normalized_email(self, email):
        return next((a for a in self.accounts.values() if a.email_normalized == email), None)

    async def get_by_id(self, brand_id):
        return self.accounts.get(brand_id)

    async def create_pending(self, *, email_normalized, brand_name, password_hash):
        now = datetime.now(timezone.utc)
        brand_id = f"test-brand-{self.next_id}"
        self.next_id += 1
        account = contract.BrandAccount(
            brand_id=brand_id, email_normalized=email_normalized, brand_name=brand_name,
            password_hash=password_hash, status=contract.BrandAccountStatus.PENDING,
            permissions=(), created_at=now, updated_at=now,
        )
        self.accounts[brand_id] = account
        return account

    async def update_status(self, *, brand_id, status, actor_id):
        old = self.accounts[brand_id]
        new = contract.BrandAccount(
            brand_id=old.brand_id, email_normalized=old.email_normalized,
            brand_name=old.brand_name, password_hash=old.password_hash, status=status,
            permissions=old.permissions, created_at=old.created_at, updated_at=datetime.now(timezone.utc),
        )
        self.accounts[brand_id] = new
        return new

    async def replace_permissions(self, *, brand_id, permissions, actor_id):
        old = self.accounts[brand_id]
        new = contract.BrandAccount(
            brand_id=old.brand_id, email_normalized=old.email_normalized,
            brand_name=old.brand_name, password_hash=old.password_hash, status=old.status,
            permissions=permissions, created_at=old.created_at, updated_at=datetime.now(timezone.utc),
        )
        self.accounts[brand_id] = new
        return new


def test_password_hash_is_salted_and_verifies():
    encoded = accounts.hash_password("a-strong-test-password")
    assert encoded != accounts.hash_password("a-strong-test-password")
    assert accounts.verify_password("a-strong-test-password", encoded)
    assert not accounts.verify_password("wrong-password", encoded)


def test_registration_normalizes_email_and_starts_pending():
    repo = FakeRepository()
    account = asyncio.run(accounts.register_brand(
        repo, email="  BRAND@Example.com ", brand_name="Example Brand",
        password="a-strong-test-password",
    ))
    assert account.email_normalized == "brand@example.com"
    assert account.status is contract.BrandAccountStatus.PENDING
    assert account.password_hash != "a-strong-test-password"


def test_pending_brand_cannot_authenticate():
    repo = FakeRepository()
    asyncio.run(accounts.register_brand(
        repo, email="brand@example.com", brand_name="Example Brand",
        password="a-strong-test-password",
    ))
    try:
        asyncio.run(accounts.authenticate_brand(
            repo, email="brand@example.com", password="a-strong-test-password",
        ))
    except accounts.BrandAccountError as exc:
        assert str(exc) == "Invalid brand credentials"
    else:
        raise AssertionError("Pending accounts must not authenticate")


def test_only_authorized_actor_can_approve_brand():
    repo = FakeRepository()
    account = asyncio.run(accounts.register_brand(
        repo, email="brand@example.com", brand_name="Example Brand",
        password="a-strong-test-password",
    ))
    try:
        asyncio.run(accounts.change_brand_status(
            repo, brand_id=account.brand_id, actor_id="reviewer",
            actor_permissions=set(), new_status=contract.BrandAccountStatus.ACTIVE,
        ))
    except accounts.BrandAccountError as exc:
        assert "permission" in str(exc).lower()
    else:
        raise AssertionError("Unauthorized actor must not approve a brand")


def test_active_brand_authenticates_with_current_repository_permissions():
    repo = FakeRepository()
    account = asyncio.run(accounts.register_brand(
        repo, email="brand@example.com", brand_name="Example Brand",
        password="a-strong-test-password",
    ))
    asyncio.run(repo.replace_permissions(
        brand_id=account.brand_id, permissions=("products:read",), actor_id="reviewer",
    ))
    asyncio.run(repo.update_status(
        brand_id=account.brand_id, status=contract.BrandAccountStatus.ACTIVE, actor_id="reviewer",
    ))
    principal = asyncio.run(accounts.authenticate_brand(
        repo, email="BRAND@example.com", password="a-strong-test-password",
    ))
    assert principal.brand_id == account.brand_id
    assert principal.permissions == ["products:read"]


def test_deleted_brand_cannot_be_reactivated():
    repo = FakeRepository()
    account = asyncio.run(accounts.register_brand(
        repo, email="brand@example.com", brand_name="Example Brand",
        password="a-strong-test-password",
    ))
    asyncio.run(repo.update_status(
        brand_id=account.brand_id, status=contract.BrandAccountStatus.DELETED, actor_id="reviewer",
    ))
    try:
        asyncio.run(accounts.change_brand_status(
            repo, brand_id=account.brand_id, actor_id="reviewer",
            actor_permissions={"brands:approve"}, new_status=contract.BrandAccountStatus.ACTIVE,
        ))
    except accounts.BrandAccountError as exc:
        assert "Deleted accounts" in str(exc)
    else:
        raise AssertionError("Deleted accounts must not be reactivated")
