import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://athar:athar_pass@localhost:5432/athar_db",
)
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/data/uploads")
