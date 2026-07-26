import hashlib
import logging
import secrets
import time
import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_twilio
from app.core.exceptions import BadRequestException, UnauthorizedException
from app.core.limiter import limiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.db.session import get_db
from app.models.provider_profile import ProviderProfile
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import OTPRequest, OTPSendResponse, OTPVerify, TokenRefresh
from app.schemas.provider import ProviderRegisterRequest, ProviderRegisterResponse
from app.schemas.user import TokenResponse, UserRead
from app.services.twilio import TwilioService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])

_otp_store: dict[str, dict] = {}
_OTP_TTL_SECONDS = 300  # 5 minutes
_OTP_MAX_STORE = 1000


def _cleanup_otp_store() -> None:
    now = time.time()
    expired = [k for k, v in _otp_store.items() if now - v["created_at"] > _OTP_TTL_SECONDS]
    for k in expired:
        del _otp_store[k]
    if len(_otp_store) > _OTP_MAX_STORE:
        oldest = sorted(_otp_store, key=lambda k: _otp_store[k]["created_at"])[:len(_otp_store) - _OTP_MAX_STORE]
        for k in oldest:
            del _otp_store[k]


@router.post("/send-otp", response_model=OTPSendResponse)
@limiter.limit("10/minute")
async def send_otp(
    body: OTPRequest,
    request: Request,  # noqa: ARG001 — required by slowapi limiter
    twilio: TwilioService = Depends(get_twilio),
):
    if twilio.is_available:
        result = await twilio.send_otp(body.phone)
        if result:
            logger.info("OTP sent via Twilio to %s", body.phone)
            return OTPSendResponse(message="OTP sent successfully")
        logger.warning("Twilio send failed, falling back for %s", body.phone)

    _cleanup_otp_store()
    code = "".join(secrets.choice("0123456789") for _ in range(6))
    _otp_store[body.phone] = {"code": code, "created_at": time.time()}
    logger.info("OTP (fallback) generated for %s (NOT returned in response)", body.phone)
    return OTPSendResponse(message="OTP sent successfully")


@router.post("/verify-otp", response_model=TokenResponse)
@limiter.limit("20/minute")
async def verify_otp(
    body: OTPVerify,
    request: Request,  # noqa: ARG001 — required by slowapi limiter
    db: AsyncSession = Depends(get_db),
    twilio: TwilioService = Depends(get_twilio),
):
    if twilio.sms_available:
        verified = await twilio.verify_otp(body.phone, body.code)
        if not verified:
            raise BadRequestException(message="Invalid or expired OTP")
    else:
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
@limiter.limit("20/minute")
async def refresh_token(body: TokenRefresh, request: Request, db: AsyncSession = Depends(get_db)):  # noqa: ARG001
    try:
        payload = decode_token(body.refresh_token)
    except Exception:
        raise UnauthorizedException(message="Invalid refresh token")

    if payload.get("type") != "refresh":
        raise UnauthorizedException(message="Invalid token type")

    user_id = payload["sub"]
    token_hash = hashlib.sha256(body.refresh_token.encode()).hexdigest()

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
    result = await db.execute(select(User).where(User.phone == phone))
    user = result.scalar_one_or_none()
    if not user:
        user = User(phone=phone)
        db.add(user)
        await db.flush()
    return user


@router.post("/register-provider", response_model=ProviderRegisterResponse)
@limiter.limit("5/minute")
async def register_provider(
    body: ProviderRegisterRequest,
    request: Request,  # noqa: ARG001 — required by slowapi
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in ("traveler", "admin"):
        raise BadRequestException(message="Already registered as a provider")

    current_user.role = body.provider_type
    await db.flush()

    profile = ProviderProfile(
        user_id=current_user.id,
        provider_type=body.provider_type,
        company_name=body.company_name,
        property_name=body.property_name,
        property_type=body.property_type,
        website=body.website,
        experience_years=body.experience_years,
        team_size=body.team_size,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)

    return ProviderRegisterResponse(
        user_id=current_user.id,
        profile_id=profile.id,
        phone=current_user.phone,
        provider_type=profile.provider_type,
        company_name=profile.company_name,
        property_name=profile.property_name,
        website=profile.website,
    )
