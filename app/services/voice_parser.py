import re
import whisper
import numpy as np


class VoiceParser:
    def __init__(self, model_name: str = "base"):
        self.model = None
        try:
            self.model = whisper.load_model(model_name)
        except Exception:
            self.model = None

    def transcribe(self, audio_bytes: bytes) -> str:
        if self.model is None:
            return ""
        import io
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name

        result = self.model.transcribe(tmp_path)
        import os

        os.unlink(tmp_path)
        return result.get("text", "")

    def extract_entities(self, text: str) -> dict:
        entities = {"origin": None, "destination": None, "mode": None}

        origin_patterns = [
            r"(?:from|min|من)\s+(\w+)",
            r"(?:au|à|a|in)\s+(\w+)",
        ]
        dest_patterns = [
            r"(?:to|à|a|ilā|الى|إلى|li|ل)\s+(\w+)",
            r"(?:vers|toward)\s+(\w+)",
        ]
        mode_keywords = {
            "taxi": ["taxi", "cab", "تاكسي", "أجرة"],
            "bus": ["bus", "autobus", "bicycle", "حافلة", "باص"],
            "train": ["train", "sncf", "القطار", "قطار"],
        }

        for pattern in origin_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                entities["origin"] = match.group(1)
                break

        for pattern in dest_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                entities["destination"] = match.group(1)
                break

        for mode, keywords in mode_keywords.items():
            if any(kw in text.lower() for kw in keywords):
                entities["mode"] = mode
                break

        return entities
