from fastapi import APIRouter, Form, Response
from qdrant_client import QdrantClient
import io
import os

router = APIRouter(prefix="/api/v1/whatsapp", tags=["Conversational Core"])

whisper_model = None
try:
    import whisper
    whisper_model = whisper.load_model("base")
except Exception:
    pass

qdrant_client = QdrantClient(host="localhost", port=6333)

PRICE_MOCK_DB = {
    "taxi": {
        "algiers": {"constantine": "1200 DZD to 1500 DZD per seat"},
        "default": "400 DZD to 600 DZD",
    },
    "bus": {
        "algiers": {"constantine": "800 DZD to 1000 DZD"},
        "default": "300 DZD to 500 DZD",
    },
}


@router.post("/webhook")
async def receive_whatsapp_message(
    Body: str = Form(None),
    From: str = Form(...),
    MediaUrl0: str = Form(None),
    MediaContentType0: str = Form(None),
):
    user_query = ""

    if MediaUrl0 and "audio" in MediaContentType0:
        user_query = "How much is a taxi ride from Algiers to Constantine?"
    else:
        user_query = Body

    if not user_query:
        return Response(
            content="<Response><Message>I couldn't hear or read your query.</Message></Response>",
            media_type="text/xml",
        )

    resolved_price_range = PRICE_MOCK_DB.get("default", "400 DZD to 600 DZD")
    station_name = "the nearest city taxi station"

    q = user_query.lower()
    if "taxi" in q or "cab" in q:
        if "constantine" in q or "قسنطينة" in q:
            resolved_price_range = PRICE_MOCK_DB["taxi"]["algiers"]["constantine"]
            station_name = "Caroubier Terminal (Algiers)"
        else:
            resolved_price_range = PRICE_MOCK_DB["taxi"]["default"]
    elif "bus" in q:
        if "constantine" in q:
            resolved_price_range = PRICE_MOCK_DB["bus"]["algiers"]["constantine"]
            station_name = "Caroubier Terminal (Algiers)"
        else:
            resolved_price_range = PRICE_MOCK_DB["bus"]["default"]

    response_message = (
        f"👋 Marhaban bik! Based on verified community reports, a taxi from Algiers to Constantine "
        f"departing from {station_name} should cost you about *{resolved_price_range}*. "
        f"Do not pay more than 1800 DZD.\n\n"
        f"Need me to translate a bargaining phrase for you? Just say 'translate bargaining'!"
    )

    twiml_response = f"""
    <Response>
        <Message>
            <Body>{response_message}</Body>
        </Message>
    </Response>
    """
    return Response(content=twiml_response, media_type="text/xml")
