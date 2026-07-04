import logging

logger = logging.getLogger(__name__)


class VoiceParser:
    def __init__(self, model_name: str = "base"):
        self.model = None
        logger.warning("VoiceParser is a stub — install openai-whisper")

    def transcribe(self, audio_bytes: bytes) -> str:
        logger.warning("VoiceParser.transcribe() called but not implemented")
        return ""

    def extract_entities(self, text: str) -> dict:
        logger.warning("VoiceParser.extract_entities() called but not implemented")
        return {"origin": None, "destination": None, "mode": None}
