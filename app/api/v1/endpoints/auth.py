import hashlib
import logging
import secrets
import time
import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_twilio
from app.core.config import settings
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
_otp_send_times: dict[str, list[float]] = {}
_OTP_TTL_SECONDS = 300  # 5 minutes
_OTP_MAX_STORE = 1000
_OTP_MAX_ATTEMPTS = 5
_OTP_SEND_LIMIT = 3
_OTP_SEND_WINDOW_SECONDS = 600  # 10 minutes


def _cleanup_otp_store() -> None:
    now = time.time()
    expired = [k for k, v in _otp_store.items() if now - v["created_at"] > _OTP_TTL_SECONDS]
    for k in expired:
        del _otp_store[k]
    if len(_otp_store) > _OTP_MAX_STORE:
        oldest = sorted(_otp_store, key=lambda k: _otp_store[k]["created_at"])[
            : len(_otp_store) - _OTP_MAX_STORE
        ]
        for k in oldest:
            del _otp_store[k]
    stale_sends = [
        k
        for k, v in _otp_send_times.items()
        if not any(now - t < _OTP_SEND_WINDOW_SECONDS for t in v)
    ]
    for k in stale_sends:
        del _otp_send_times[k]


def _phone_can_request_otp(phone: str) -> tuple[bool, int]:
    """Per-phone send throttle to blunt SMS-bombing/abuse of the fallback."""
    now = time.time()
    recent = [t for t in _otp_send_times.get(phone, []) if now - t < _OTP_SEND_WINDOW_SECONDS]
    if len(recent) >= _OTP_SEND_LIMIT:
        _otp_send_times[phone] = recent
        return False, 0
    recent.append(now)
    _otp_send_times[phone] = recent
    return True, _OTP_SEND_LIMIT - len(recent) - 1


@router.post(
    "/send-otp",
    response_model=OTPSendResponse,
    summary="Send one-time password",
    description=(
        "Request a 6-digit OTP for passwordless login. When Twilio is configured the code is "
        "delivered by SMS; otherwise it is generated in-memory (never returned in the response). "
        "Rate limited to 10/minute globally and 3 sends per phone per 10 minutes."
    ),
    responses={
        400: {"description": "Too many OTP requests for this number (per-phone throttling)"},
        429: {"description": "Global rate limit exceeded (10/minute)"},
    },
)
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
    allowed, _remaining = _phone_can_request_otp(body.phone)
    if not allowed:
        raise BadRequestException(
            message="Too many OTP requests for this number. Try again in a few minutes."
        )
    code = "".join(secrets.choice("0123456789") for _ in range(6))
    _otp_store[body.phone] = {"code": code, "created_at": time.time(), "attempts": 0}
    logger.info("OTP (fallback) generated for %s (NOT returned in response)", body.phone)
    return OTPSendResponse(message="OTP sent successfully")


@router.post(
    "/verify-otp",
    response_model=TokenResponse,
    summary="Verify OTP and log in",
    description=(
        "Exchange a phone + OTP for an access token and refresh token. Creates the user account "
        "on first login. A code is invalidated after 5 failed attempts (constant-time comparison). "
        "The refresh token is stored hashed with a rotation family."
    ),
    responses={
        400: {"description": "Invalid or expired OTP, or too many attempts — request a new code"},
        429: {"description": "Rate limit exceeded (20/minute)"},
    },
)
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
    elif settings.debug and secrets.compare_digest(body.code, settings.debug_otp):
        # Dev-only fixed OTP — accepted solely when debug=True. Codes are never
        # accepted in production (debug defaults to False).
        pass
    else:
        stored = _otp_store.get(body.phone)
        if not stored:
            raise BadRequestException(message="Invalid or expired OTP")
        attempts = stored.get("attempts", 0)
        if attempts >= _OTP_MAX_ATTEMPTS:
            del _otp_store[body.phone]
            raise BadRequestException(message="Too many attempts. Request a new OTP.")
        if not secrets.compare_digest(stored["code"], body.code):
            stored["attempts"] = attempts + 1
            if stored["attempts"] >= _OTP_MAX_ATTEMPTS:
                del _otp_store[body.phone]
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


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate tokens",
    description=(
        "Exchange a valid refresh token for a fresh access/refresh pair. Rotation is one-time-use: "
        "presenting an already-revoked token revokes the entire token family (stolen-token detection)."  # noqa: E501
    ),
    responses={
        401: {"description": "Invalid, expired, or revoked refresh token"},
        429: {"description": "Rate limit exceeded (20/minute)"},
    },
)
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
    if not stored:
        raise UnauthorizedException(message="Token has been revoked")
    if stored.is_revoked:
        # A revoked token being presented again is a strong signal the token
        # was stolen and replayed after legitimate rotation. Revoke the whole
        # family so any rotated peers are invalidated too.
        await db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.family == stored.family,
                RefreshToken.is_revoked.is_(False),
            )
            .values(is_revoked=True)
        )
        await db.commit()
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


@router.post(
    "/register-provider",
    response_model=ProviderRegisterResponse,
    summary="Register as a provider",
    description=(
        "Upgrade the authenticated user's account to a provider (guide/agency/hotel) and create "
        "their provider profile. Only users with the `traveler` role (or admins) can register; "
        "rate limited to 5/minute."
    ),
    responses={
        400: {"description": "Already registered as a provider"},
        401: {"description": "Authentication required"},
        429: {"description": "Rate limit exceeded (5/minute)"},
    },
)
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
