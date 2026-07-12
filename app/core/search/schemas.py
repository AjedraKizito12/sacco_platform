from __future__ import annotations

from pydantic import BaseModel


class SearchHitOut(BaseModel):
    entity_type: str
    id: str
    title: str
    subtitle: str
    url: str
    status: str = ""
    status_entity: str = ""


class SearchResultsOut(BaseModel):
    hits: list[SearchHitOut]
    took_ms: int
