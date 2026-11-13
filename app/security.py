import hashlib
import hmac
import secrets

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Device

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def new_device_key() -> str:
    return "dev_" + secrets.token_urlsafe(32)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _unauthorized() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or invalid API key")


def require_admin(key: str | None = Security(api_key_header)) -> None:
    expected = get_settings().admin_api_key
    if not key or not hmac.compare_digest(key, expected):
        raise _unauthorized()


def require_device(
    key: str | None = Security(api_key_header), db: Session = Depends(get_db)
) -> Device:
    if not key:
        raise _unauthorized()
    device = db.scalar(select(Device).where(Device.api_key_hash == hash_key(key)))
    if device is None:
        raise _unauthorized()
    return device
