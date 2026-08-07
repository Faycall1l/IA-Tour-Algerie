import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from app.core.config import settings

_cached_priv: str | None = None
_cached_pub: str | None = None

_KEY_FILE = Path(__file__).resolve().parent.parent.parent / "secrets" / "jwt_ed25519.pem"


def _get_keys() -> tuple[str, str]:
    """Return the signing key pair.

    Priority: env-configured keys > persisted generated key > generate + persist.
    Persisting avoids invalidating tokens on every restart and keeps all
    uvicorn workers signing with the same key.
    """
    global _cached_priv, _cached_pub
    if _cached_priv and _cached_pub:
        return _cached_priv, _cached_pub
    if settings.auth.jwt_private_key:
        _cached_priv = settings.auth.jwt_private_key
        _cached_pub = settings.auth.jwt_public_key
        return _cached_priv, _cached_pub
    if _KEY_FILE.exists():
        _cached_priv = _KEY_FILE.read_text().strip()
        private_key = serialization.load_pem_private_key(_cached_priv.encode(), password=None)
        _cached_pub = (
            private_key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode()
        )
        return _cached_priv, _cached_pub
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    _cached_priv = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    _cached_pub = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    try:
        _KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        _KEY_FILE.write_text(_cached_priv)
        _KEY_FILE.chmod(0o600)
    except OSError:
        pass
    return _cached_priv, _cached_pub


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
