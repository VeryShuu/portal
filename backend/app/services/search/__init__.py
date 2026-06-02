"""Search service: filters, per-entity queries, and multi/suggest use-cases."""

from app.services.search.aggregate import run_multi_search, run_suggest
from app.services.search.entities import (
    search_articles,
    search_links,
    search_news,
    search_users,
)
from app.services.search.filters import (
    DATETIME_MIN_UTC,
    HL_OPTIONS,
    article_conditions,
    escape_like,
    link_conditions,
    news_conditions,
    user_conditions,
)

__all__ = [
    "DATETIME_MIN_UTC",
    "HL_OPTIONS",
    "article_conditions",
    "escape_like",
    "link_conditions",
    "news_conditions",
    "run_multi_search",
    "run_suggest",
    "search_articles",
    "search_links",
    "search_news",
    "search_users",
    "user_conditions",
]
