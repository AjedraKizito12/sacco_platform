from __future__ import annotations

from elasticsearch import AsyncElasticsearch

from app.core.config import get_settings


def get_search_client() -> AsyncElasticsearch:
    return AsyncElasticsearch(get_settings().elasticsearch_url)
