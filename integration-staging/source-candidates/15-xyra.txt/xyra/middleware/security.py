"""
Security middleware for authentication and rate limiting.
"""
from fastapi.security import HTTPBearer
from fastapi.responses import JSONResponse
import jwt
import os
from ..connection_pool import SecureConnectionPool
from ..config import XyraConfig

security = HTTPBearer()

class SecurityMiddleware:
    def __init__(self, config: XyraConfig):
        self.config = config
        self.secret_key = os.getenv("JWT_SECRET", config.JWT_SECRET)
        self.algorithm = "HS256"

    async def __call__(self, request, call_next):
        token = request.headers.get("Authorization")
        if not token or not token.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"error": "Missing or invalid token"}
            )
        try:
            payload = jwt.decode(
                token[7:],
                self.secret_key,
                algorithms=[self.algorithm]
            )
            request.state.user_id = payload["sub"]
            request.state.role = payload.get("role", "user")
        except jwt.ExpiredSignatureError:
            return JSONResponse(
                status_code=401,
                content={"error": "Token expired"}
            )
        except jwt.InvalidTokenError:
            return JSONResponse(
                status_code=401,
                content={"error": "Invalid token"}
            )

        endpoint = request.url.path
        pool = await SecureConnectionPool.get_instance()
        if not await pool.check_rate_limit(request.state.user_id, endpoint):
            return JSONResponse(
                status_code=429,
                content={"error": "Rate limit exceeded", "retry_after": 60},
                headers={"Retry-After": "60"}
            )

        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
