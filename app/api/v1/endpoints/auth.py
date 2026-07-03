import hashlib
import logging
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, UnauthorizedException
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.db.session import get_db
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import OTPRequest, OTPVerify, TokenRefresh
from app.schemas.user import TokenResponse, UserRead

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])

_otp_store: dict[str, dict] = {}


@router.post("/send-otp")
async def send_otp(body: OTPRequest):
    code = "123456"
    _otp_store[body.phone] = {"code": code}
    logger.info(f"OTP for {body.phone}: {code}")
    return {"message": "OTP sent successfully", "otp": code}


@router.post("/verify-otp", response_model=TokenResponse)
async def verify_otp(body: OTPVerify, db: AsyncSession = Depends(get_db)):
    stored = _otp_store.get(body.phone)
    if not stored or stored["code"] != body.code:
        raise BadRequestException(message="Invalid or expired OTP")

    del _otp_store[body.phone]

    user = await _get_or_create_user(db, body.phone)
    access_token = create_access_token(str(user.id), user.role)
    refresh_token_str = create_refresh_token(str(user.id))

    family = str(uuid.uuid4())
    token_hash = hashlib.sha256(refresh_token_str.encode()).hexdigest()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            family=family,
        )
    )
    await db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token_str,
        user=UserRead.model_validate(user),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(body: TokenRefresh, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(body.refresh_token)
    except Exception:
        raise UnauthorizedException(message="Invalid refresh token")

    if payload.get("type") != "refresh":
        raise UnauthorizedException(message="Invalid token type")

    user_id = payload["sub"]
    token_hash = hashlib.sha256(body.refresh_token.encode()).hexdigest()

    from sqlalchemy import select

    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    stored = result.scalar_one_or_none()
    if not stored or stored.is_revoked:
        raise UnauthorizedException(message="Token has been revoked")

    stored.is_revoked = True

    user = await db.get(User, uuid.UUID(user_id))
    if not user:
        raise UnauthorizedException(message="User not found")

    new_access = create_access_token(str(user.id), user.role)
    new_refresh = create_refresh_token(str(user.id))

    new_entry = RefreshToken(
        user_id=user.id,
        token_hash=hashlib.sha256(new_refresh.encode()).hexdigest(),
        family=stored.family,
    )
    db.add(new_entry)
    await db.commit()

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        user=UserRead.model_validate(user),
    )


async def _get_or_create_user(db: AsyncSession, phone: str) -> User:
    from sqlalchemy import select

    result = await db.execute(select(User).where(User.phone == phone))
    user = result.scalar_one_or_none()
    if not user:
        user = User(phone=phone)
        db.add(user)
        await db.flush()
    return user
