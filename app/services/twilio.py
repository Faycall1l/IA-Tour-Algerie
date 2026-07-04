import asyncio
import logging

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from app.core.config import settings

logger = logging.getLogger(__name__)


class TwilioService:
    def __init__(self) -> None:
        self._client: Client | None = None
        self._verify_sid: str | None = None
        if settings.twilio.account_sid and settings.twilio.auth_token:
            self._client = Client(settings.twilio.account_sid, settings.twilio.auth_token)
            self._verify_sid = settings.twilio.verify_service_sid
            logger.info("Twilio client initialized")
        else:
            logger.warning("Twilio credentials not configured — OTP uses fallback")

    @property
    def is_available(self) -> bool:
        return self._client is not None

    @property
    def sms_available(self) -> bool:
        return self._client is not None and bool(self._verify_sid)

    @property
    def whatsapp_available(self) -> bool:
        return self._client is not None and bool(self._whatsapp_from)

    async def send_otp(self, phone: str) -> dict | None:
        if not self.sms_available:
            return None
        loop = asyncio.get_running_loop()
        try:
            verification = await loop.run_in_executor(
                None,
                lambda: self._client.verify.v2.services(self._verify_sid).verifications.create(
                    to=phone, channel="sms"
                ),
            )
            logger.info("OTP sent via Twilio to %s (sid=%s)", phone, verification.sid)
            return {"sid": verification.sid, "status": verification.status}
        except TwilioRestException as exc:
            logger.error("Twilio send-OTP failed for %s: %s", phone, exc)
            return None

    @property
    def _whatsapp_from(self) -> str | None:
        if not settings.twilio.whatsapp_from:
            return None
        return f"whatsapp:{settings.twilio.whatsapp_from}"

    async def send_whatsapp(self, to_phone: str, message: str) -> bool:
        if not self._client or not self._whatsapp_from:
            logger.warning("WhatsApp not configured — skipping message to %s", to_phone)
            return False
        loop = asyncio.get_running_loop()
        try:
            msg = await loop.run_in_executor(
                None,
                lambda: self._client.messages.create(
                    to=f"whatsapp:{to_phone}",
                    from_=self._whatsapp_from,
                    body=message,
                ),
            )
            logger.info("WhatsApp sent to %s (sid=%s)", to_phone, msg.sid)
            return True
        except TwilioRestException as exc:
            logger.error("WhatsApp send failed for %s: %s", to_phone, exc)
            return False

    async def verify_otp(self, phone: str, code: str) -> bool:
        if not self.sms_available:
            return False
        loop = asyncio.get_running_loop()
        try:
            check = await loop.run_in_executor(
                None,
                lambda: self._client.verify.v2.services(
                    self._verify_sid
                ).verification_checks.create(to=phone, code=code),
            )
            if check.status == "approved":
                logger.info("OTP verified via Twilio for %s", phone)
                return True
            logger.warning("OTP check failed for %s: status=%s", phone, check.status)
            return False
        except TwilioRestException as exc:
            logger.error("Twilio verify-OTP failed for %s: %s", phone, exc)
            return False
