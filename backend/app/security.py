import hmac
import os

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer(auto_error=False)


async def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Security(security),
):
    """
    Verify API key authentication.

    If PATCHPILOT_API_KEY is not configured, authentication is disabled.
    This preserves compatibility for local development and automated tests.
    """
    # Read the environment variable per-request to support hot rotation of the API key
    # without requiring a server restart (harmless in practice as the OS caches reads).
    api_key = os.getenv("PATCHPILOT_API_KEY")

    # Authentication disabled if no API key is configured.
    if not api_key:
        return True

    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not hmac.compare_digest(credentials.credentials, api_key):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return True
