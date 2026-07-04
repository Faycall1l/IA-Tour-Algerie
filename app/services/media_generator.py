import logging

logger = logging.getLogger(__name__)


class MediaGenerator:
    def __init__(self):
        logger.warning("MediaGenerator is a stub — install opencv-python, gTTS, etc.")

    def stabilize_video(self, input_path: str, output_path: str | None = None) -> dict:
        logger.warning("MediaGenerator.stabilize_video() called but not implemented")
        return {"status": "error", "message": "Not implemented (stub)"}
