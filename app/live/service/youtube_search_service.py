"""Servicio de búsqueda musical en YouTube Data API v3 para el DJ Virtual Autónomo."""

from __future__ import annotations

import html
import logging
from typing import Any

import httpx

from app.core.config import Settings, settings as default_settings

logger = logging.getLogger(__name__)

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


class YoutubeMusicSearchService:
    """Busca pistas/sets embebibles en YouTube usando la API oficial v3."""

    def __init__(self, config: Settings | None = None) -> None:
        self.settings = config or default_settings
        self.http = httpx.Client(timeout=10.0)

    def search(self, query: str, *, max_results: int = 5) -> list[dict[str, Any]]:
        """Devuelve videos musicales embebibles de YouTube para una consulta dada."""
        api_key = (self.settings.YOUTUBE_API_KEY or "").strip()
        clean_query = (query or "").strip()
        if not api_key or not clean_query:
            return []

        params = {
            "part": "snippet",
            "type": "video",
            "videoEmbeddable": "true",
            "videoCategoryId": "10",  # Music
            "maxResults": max(1, min(10, max_results)),
            "q": clean_query,
            "key": api_key,
        }
        response = self.http.get(YOUTUBE_SEARCH_URL, params=params)
        if response.status_code != 200:
            logger.warning(
                "YouTube Data API devolvió %s: %s",
                response.status_code,
                response.text[:250],
            )
            response.raise_for_status()

        data = response.json()
        tracks: list[dict[str, Any]] = []
        for item in data.get("items", []):
            video_id = item.get("id", {}).get("videoId")
            snippet = item.get("snippet", {})
            if not video_id:
                continue
            thumbs = snippet.get("thumbnails", {})
            thumb_url = (
                thumbs.get("medium", {}).get("url")
                or thumbs.get("default", {}).get("url")
                or ""
            )
            tracks.append(
                {
                    "video_id": str(video_id),
                    "title": html.unescape(str(snippet.get("title", ""))),
                    "channel": html.unescape(str(snippet.get("channelTitle", ""))),
                    "thumbnail": str(thumb_url),
                }
            )
        return tracks


_youtube_service: YoutubeMusicSearchService | None = None


def get_youtube_music_search_service() -> YoutubeMusicSearchService:
    global _youtube_service
    if _youtube_service is None:
        _youtube_service = YoutubeMusicSearchService()
    return _youtube_service
