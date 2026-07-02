from fastapi import FastAPI
from app.routers import admin_visa, whatsapp_bot, studio_media

app = FastAPI(
    title="ATHAR OS (أثر)",
    description="Sovereign Algerian AI Tourism Platform",
    version="0.1.0",
)

app.include_router(admin_visa.router)
app.include_router(whatsapp_bot.router)
app.include_router(studio_media.router)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "project": "ATHAR OS"}
