from __future__ import annotations

import asyncio
from html import unescape

from googleapiclient.discovery import build

from src.models import YouTubeResult


class YouTubeService:
    def __init__(self, api_key: str) -> None:
        self._service = build("youtube", "v3", developerKey=api_key)

    async def search_music(self, query: str, limit: int = 3) -> list[YouTubeResult]:
        return await asyncio.to_thread(self._search_music_sync, query, limit)

    def _search_music_sync(self, query: str, limit: int) -> list[YouTubeResult]:
        request = self._service.search().list(
            part="snippet",
            q=query,
            type="video",
            maxResults=limit,
            videoCategoryId="10",
            videoEmbeddable="true",
        )
        response = request.execute()

        results: list[YouTubeResult] = []
        for item in response.get("items", []):
            video_id = item.get("id", {}).get("videoId")
            snippet = item.get("snippet", {})
            title = unescape(snippet.get("title", "제목 없음"))
            artist = unescape(snippet.get("channelTitle", ""))
            thumbnails = snippet.get("thumbnails", {})
            thumbnail_url = (
                thumbnails.get("high", {}).get("url")
                or thumbnails.get("medium", {}).get("url")
                or thumbnails.get("default", {}).get("url")
            )
            if not video_id:
                continue
            results.append(
                YouTubeResult(
                    title=title,
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    artist=artist,
                    thumbnail_url=thumbnail_url,
                )
            )
        return results
