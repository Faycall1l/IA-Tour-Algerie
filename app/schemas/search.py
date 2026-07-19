import uuid

from pydantic import BaseModel, Field


class SuggestItem(BaseModel):
    entity_type: str
    entity_id: uuid.UUID
    name: str
    category: str | None = None
    wilaya_id: int | None = None
    photo_url: str | None = None


class SuggestFeed(BaseModel):
    query: str
    items: list[SuggestItem]


class SearchResult(BaseModel):
    entity_type: str
    entity_id: uuid.UUID
    name: str
    name_en: str | None = None
    name_ar: str | None = None
    description: str | None = None
    category: str | None = None
    subtype: str | None = None
    wilaya_id: int | None = None
    commune: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    photo_url: str | None = None
    price_dzd: float | None = Field(None, alias="price")
    rank: float | None = None


class SearchFeed(BaseModel):
    query: str
    results: list[SearchResult]
    total: int
    page: int
    page_size: int
    total_pages: int
