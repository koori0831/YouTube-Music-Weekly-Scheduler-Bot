from __future__ import annotations

import asyncio
from html import unescape
from typing import Any

from ytmusicapi import YTMusic

from src.models import YouTubeResult


class YouTubeService:
    def __init__(self, api_key: str | None = None) -> None:
        # ytmusicapi public search does not require API key.
        self._service = YTMusic()

    async def search_music(self, query: str, limit: int = 3) -> list[YouTubeResult]:
        return await asyncio.to_thread(self._search_music_sync, query, limit)

    def _search_music_sync(self, query: str, limit: int) -> list[YouTubeResult]:
        primary_items = self._service.search(query, filter="songs", limit=limit)

        fallback_items: list[dict[str, Any]] = []
        if len(primary_items) < limit:
            fallback_items = self._service.search(query, filter="videos", limit=limit * 2)

        seen_video_ids: set[str] = set()
        results: list[YouTubeResult] = []

        for item in [*primary_items, *fallback_items]:
            video_id = str(item.get("videoId", "")).strip()
            if not video_id or video_id in seen_video_ids:
                continue

            seen_video_ids.add(video_id)

            title = unescape(str(item.get("title", "제목 없음")))

            artist = ""
            artists = item.get("artists", [])
            if isinstance(artists, list) and artists:
                first_artist = artists[0]
                if isinstance(first_artist, dict):
                    artist = unescape(str(first_artist.get("name", "")))

            thumbnail_url = None
            thumbnails = item.get("thumbnails", [])
            if isinstance(thumbnails, list) and thumbnails:
                # usually larger image is at the end
                thumbnail_url = str(thumbnails[-1].get("url", "")).strip() or None

            results.append(
                YouTubeResult(
                    title=title,
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    artist=artist,
                    thumbnail_url=thumbnail_url,
                )
            )

            if len(results) >= limit:
                break

        return results
