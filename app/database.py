from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from qdrant_client import QdrantClient
from app.config import DATABASE_URL, QDRANT_HOST, QDRANT_PORT

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
