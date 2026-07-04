import logging

logger = logging.getLogger(__name__)


class OCREngine:
    def __init__(self, model_type: str = "tesseract"):
        self.model_type = model_type
        logger.warning("OCREngine is a stub — install pytesseract/tesseract")

    def extract_text(self, image_bytes: bytes) -> str:
        logger.warning("OCREngine.extract_text() called but not implemented")
        return ""

    def parse_mrz(self, ocr_text: str) -> dict:
        logger.warning("OCREngine.parse_mrz() called but not implemented")
        return {}
