"""Brand account lifecycle logic requiring an authoritative repository adapter."""
from __future__ import annotations
import base64, hashlib, hmac, re, secrets
try:
    from .repository_contract import BrandAccount, BrandAccountRepository, BrandAccountStatus
    from .token_security import BrandPrincipal
except ImportError:
    from repository_contract import BrandAccount, BrandAccountRepository, BrandAccountStatus
    from token_security import BrandPrincipal

_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


class BrandAccountError(ValueError):
    """Safe-to-handle account lifecycle error."""


def normalize_email(email: str) -> str:
    if not isinstance(email, str):
        raise BrandAccountError("A valid email address is required")
    normalized = email.strip().casefold()
    if len(normalized) > 254 or not _EMAIL.fullmatch(normalized):
        raise BrandAccountError("A valid email address is required")
    return normalized


def hash_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < 12 or len(password) > 1024:
        raise BrandAccountError("Password must be between 12 and 1024 characters")
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    salt64 = base64.urlsafe_b64encode(salt).decode("ascii")
    key64 = base64.urlsafe_b64encode(derived).decode("ascii")
    return "$scrypt$%d$%d$%d$%s$%s" % (_SCRYPT_N, _SCRYPT_R, _SCRYPT_P, salt64, key64)


def verify_password(password: str, encoded: str) -> bool:
    try:
        parts = encoded.split("$")
        if len(parts) != 7 or parts[1] != "scrypt":
            return False
        n, r, p = int(parts[2]), int(parts[3]), int(parts[4])
        if (n, r, p) != (_SCRYPT_N, _SCRYPT_R, _SCRYPT_P):
            return False
        salt = base64.urlsafe_b64decode(parts[5].encode("ascii"))
        expected = base64.urlsafe_b64decode(parts[6].encode("ascii"))
        actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=len(expected))
        return hmac.compare_digest(actual, expected)
    except (AttributeError, TypeError, ValueError, IndexError):
        return False


async def register_brand(repository: BrandAccountRepository, *, email: str, brand_name: str, password: str) -> BrandAccount:
    normalized = normalize_email(email)
    if not isinstance(brand_name, str) or not 2 <= len(brand_name.strip()) <= 120:
        raise BrandAccountError("Brand name must be between 2 and 120 characters")
    if await repository.get_by_normalized_email(normalized) is not None:
        raise BrandAccountError("Unable to register this account")
    return await repository.create_pending(
        email_normalized=normalized, brand_name=brand_name.strip(), password_hash=hash_password(password)
    )


async def authenticate_brand(repository: BrandAccountRepository, *, email: str, password: str) -> BrandPrincipal:
    try:
        normalized = normalize_email(email)
    except BrandAccountError:
        normalized = ""
    account = await repository.get_by_normalized_email(normalized) if normalized else None
    valid = account is not None and verify_password(password, account.password_hash)
    if not valid or account is None or account.status is not BrandAccountStatus.ACTIVE:
        raise BrandAccountError("Invalid brand credentials")
    return BrandPrincipal(
        brand_id=account.brand_id, brand_name=account.brand_name,
        email=account.email_normalized, permissions=list(account.permissions), role="brand_partner",
    )


async def change_brand_status(repository: BrandAccountRepository, *, brand_id: str, actor_id: str,
                              actor_permissions: set[str], new_status: BrandAccountStatus) -> BrandAccount:
    if "brands:approve" not in actor_permissions:
        raise BrandAccountError("Insufficient permission to change brand status")
    if new_status not in {BrandAccountStatus.ACTIVE, BrandAccountStatus.SUSPENDED, BrandAccountStatus.DELETED}:
        raise BrandAccountError("Unsupported target account status")
    return await repository.update_status(brand_id=brand_id, status=new_status, actor_id=actor_id)
