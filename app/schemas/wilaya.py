from pydantic import BaseModel, ConfigDict


class WilayaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name_ar: str
    name_fr: str
    name_en: str
    name_tz: str | None
    latitude: float | None
    longitude: float | None
