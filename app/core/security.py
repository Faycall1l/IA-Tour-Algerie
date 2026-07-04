import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from app.core.config import settings


def _get_keys() -> tuple[str, str]:
    if settings.auth.jwt_private_key:
        return settings.auth.jwt_private_key, settings.auth.jwt_public_key
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


def _privkey() -> str:
    return _get_keys()[0]


def _pubkey() -> str:
    return _get_keys()[1]


def create_access_token(subject: str, role: str = "traveler") -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "role": role,
        "type": "access",
        "iss": settings.app_name,
        "aud": settings.app_name,
        "iat": now,
        "exp": now + timedelta(minutes=settings.auth.access_token_expire_minutes),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _privkey(), algorithm=settings.auth.jwt_algorithm)


def create_refresh_token(subject: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "type": "refresh",
        "iss": settings.app_name,
        "aud": settings.app_name,
        "iat": now,
        "exp": now + timedelta(days=settings.auth.refresh_token_expire_days),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _privkey(), algorithm=settings.auth.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        _pubkey(),
        algorithms=[settings.auth.jwt_algorithm],
        audience=settings.app_name,
        issuer=settings.app_name,
        options={"require": ["exp", "iat", "iss", "aud", "jti"]},
    )
