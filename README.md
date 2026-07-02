# ATHAR OS (أثر) — AI-Powered Sovereign Tourism Platform

**ATHAR OS** is a sovereign, AI-powered tourism platform built for Algeria. It processes B2B visa applications via OCR, provides a WhatsApp-based conversational travel assistant with real-time price intelligence, and offers low-tech video stabilization for local artisans.

> Entry for the **AI Tour Algérie 2026** hackathon.

## Features

| Module | Route | Description |
|--------|-------|-------------|
| **Visa Automation** | `/api/v1/visa/process-passport` | MRZ passport OCR + official Excel dossier generation |
| **WhatsApp Bot** | `/api/v1/whatsapp/webhook` | Twilio webhook with Whisper voice transcription & Qdrant price lookup |
| **Artisan Studio** | `/api/v1/studio/refine-video` | OpenCV-based video stabilization for low-end phone footage |

## Tech Stack

- **Backend:** FastAPI (Python)
- **Database:** PostgreSQL + Qdrant (vector DB)
- **Speech:** OpenAI Whisper (local)
- **Vision:** OpenCV, Tesseract / LayoutLMv3
- **Infrastructure:** Designed for Algerian national cloud (Algerie Telecom / Icosnet)

## Quick Start

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Architecture

```
athar-os-prototype/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models/          # SQLAlchemy + Qdrant payload schemas
│   ├── routers/         # API endpoints
│   ├── services/        # Business logic (OCR, voice, media)
├── templates/           # Excel templates (Ministry format)
└── requirements.txt
```

## License

MIT
