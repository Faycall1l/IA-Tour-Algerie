from pydantic import BaseModel


class ServiceStatus(BaseModel):
    name: str
    status: str
    latency_ms: float | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    services: list[ServiceStatus]
