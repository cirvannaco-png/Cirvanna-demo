"""Dedicated authentication for private DSI-internal API callers."""
from __future__ import annotations

import hmac
import os
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette import status

bearer = HTTPBearer(auto_error=False)


def require_dsi_api_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    expected = os.getenv("DSI_INTERNAL_API_TOKEN", "")
    if len(expected.encode("utf-8")) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "DSI_API_AUTH_NOT_CONFIGURED"},
        )
    if credentials is None or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED"},
            headers={"WWW-Authenticate": "Bearer"},
        )
