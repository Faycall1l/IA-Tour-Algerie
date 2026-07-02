import re


class OCREngine:
    def __init__(self, model_type: str = "tesseract"):
        self.model_type = model_type

    def extract_text(self, image_bytes: bytes) -> str:
        return ""

    def parse_mrz(self, ocr_text: str) -> dict:
        mrz_lines = [
            line.strip().upper()
            for line in ocr_text.split("\n")
            if len(line.strip()) >= 44
        ]
        if len(mrz_lines) < 2:
            return {}

        line2 = mrz_lines[-1]
        line1 = mrz_lines[-2]

        try:
            return {
                "passport_number": line2[0:9].replace("<", ""),
                "nationality": line2[10:13],
                "dob": line2[13:19],
                "gender": line2[20],
                "expiry_date": line2[21:27],
                "last_name": line1[5:].split("<<")[0].replace("<", " ").strip(),
                "first_name": (
                    line1[5:].split("<<")[1].replace("<", " ").strip()
                    if len(line1[5:].split("<<")) > 1
                    else ""
                ),
            }
        except Exception:
            return {}
