"""
Authentication module for securing API endpoints against unauthorized CLI uploads.
"""

import logging
import secrets
from typing import Final

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.esm_data.database import get_db_session
from backend.esm_data.db_models import ApiToken

__all__ = ["generate_secure_token_string", "verify_api_token"]

logger: Final[logging.Logger] = logging.getLogger(__name__)

# FastAPI security scheme for Swagger UI and dependency injection
security_scheme = HTTPBearer(auto_error=False)


def generate_secure_token_string() -> str:
    """
    Creates a mathematically secure, url-safe token string.
    """
    return secrets.token_urlsafe(32)


async def verify_api_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> ApiToken:
    """
    FastAPI dependency to validate incoming HTTP Bearer tokens.
    Uses negative guard clauses to instantly reject invalid requests.
    """
    if credentials is None:
        logger.warning("Authentication failed: No bearer token provided.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Missing authentication token. "
                "Please use 'esm-tracker init --token <TOKEN>'"
            ),
            headers={"WWW-Authenticate": "Bearer"},
        )

    provided_token_string: str = credentials.credentials
    if not provided_token_string:
        logger.warning("Authentication failed: Provided token string is empty.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Empty authentication token provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Use a direct lookup for the primary key
    found_token: ApiToken | None = await session.get(ApiToken, provided_token_string)

    if found_token is None:
        logger.warning("Authentication failed: Token not found in database.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Invalid authentication token. "
                "Please generate a new one from the Streamlit app."
            ),
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not found_token.is_active:
        logger.warning("Authentication failed: Token is explicitly marked as inactive.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has been revoked or deactivated.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return found_token
