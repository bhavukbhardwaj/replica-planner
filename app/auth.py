import hmac
import os

from fastapi import Header, HTTPException


def require_token(x_api_token: str | None = Header(default=None)) -> None:
    """Shared-secret check (prototype only). Header: X-API-Token; secret: env PLAN_API_TOKEN."""
    expected = os.environ.get("PLAN_API_TOKEN", "")
    if not expected or not x_api_token or not hmac.compare_digest(x_api_token, expected):
        raise HTTPException(status_code=401, detail="invalid or missing API token")
