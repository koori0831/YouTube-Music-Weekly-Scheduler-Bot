from __future__ import annotations

import asyncio
import json
import os
import re
from html import unescape
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from ytmusicapi import YTMusic

from src.models import YouTubeResult


class YouTubeService:
    def __init__(self, api_key: str | None = None) -> None:
        # ytmusicapi public search does not require API key.
        self._service = YTMusic(language="ko", location="KR")
        proxy = self._resolve_proxy()
        if proxy:
            self._service.proxies = {"http": proxy, "https": proxy}
        self._api_key = api_key

    def _resolve_proxy(self) -> str | None:
        proxies_raw = os.getenv("YTMUSIC_PROXIES", "")
        if proxies_raw.strip():
            addresses = [entry.strip() for entry in re.split(r"[,\r\n;]+", proxies_raw) if entry.strip()]
            if addresses:
                return addresses[0]

        proxy = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
        if proxy and proxy.strip():
            return proxy.strip()
        return None

    async def search_music(self, query: str, limit: int = 3) -> list[YouTubeResult]:
        return await asyncio.to_thread(self._search_music_sync, query, limit)

    def _search_music_sync(self, query: str, limit: int) -> list[YouTubeResult]:
        primary_items = self._service.search(query, filter="songs", limit=limit)

        fallback_items: list[dict[str, Any]] = []
        if len(primary_items) < limit:
            fallback_items = self._service.search(query, filter="videos", limit=limit * 2)

        seen_video_ids: set[str] = set()
        candidate_items: list[tuple[str, dict[str, Any]]] = []

        for item in [*primary_items, *fallback_items]:
            video_id = str(item.get("videoId", "")).strip()
            if not video_id or video_id in seen_video_ids:
                continue

            seen_video_ids.add(video_id)
            candidate_items.append((video_id, item))
            if len(candidate_items) >= limit:
                break

        metadata_by_id = self._fetch_video_metadata([video_id for video_id, _ in candidate_items])

        results: list[YouTubeResult] = []
        for video_id, item in candidate_items:
            metadata = metadata_by_id.get(video_id, {})
            snippet = metadata.get("snippet", {}) if isinstance(metadata, dict) else {}

            title = unescape(
                str(
                    (snippet.get("title") if isinstance(snippet, dict) else None)
                    or item.get("title")
                    or "제목 없음"
                )
            )
            artist = self._extract_artist(snippet, item)
            thumbnail_url = self._extract_thumbnail_url(snippet, item)
            duration_seconds = self._extract_duration_seconds(metadata, item)

            results.append(
                YouTubeResult(
                    title=title,
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    artist=artist,
                    thumbnail_url=thumbnail_url,
                    duration_seconds=duration_seconds,
                )
            )

        return results

    def _extract_artist(self, snippet: dict[str, Any], search_item: dict[str, Any]) -> str:
        if isinstance(snippet, dict):
            channel_title = str(snippet.get("channelTitle", "")).strip()
            if channel_title:
                return self._normalize_artist(channel_title)

        artist = ""
        artists = search_item.get("artists", [])
        if isinstance(artists, list) and artists:
            first_artist = artists[0]
            if isinstance(first_artist, dict):
                artist = unescape(str(first_artist.get("name", "")))

        return self._normalize_artist(artist)

    def _extract_thumbnail_url(self, snippet: dict[str, Any], search_item: dict[str, Any]) -> str | None:
        if isinstance(snippet, dict):
            snippet_thumbnails = snippet.get("thumbnails", {})
            if isinstance(snippet_thumbnails, dict) and snippet_thumbnails:
                best_url = None
                best_size = -1
                for thumb_data in snippet_thumbnails.values():
                    if not isinstance(thumb_data, dict):
                        continue
                    url = str(thumb_data.get("url", "")).strip()
                    if not url:
                        continue
                    width = int(thumb_data.get("width", 0) or 0)
                    height = int(thumb_data.get("height", 0) or 0)
                    size = width * height
                    if size > best_size:
                        best_size = size
                        best_url = url
                if best_url:
                    return best_url

        thumbnails = search_item.get("thumbnails", [])
        if isinstance(thumbnails, list) and thumbnails:
            # usually larger image is at the end
            return str(thumbnails[-1].get("url", "")).strip() or None

        return None

    def _fetch_video_metadata(self, video_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not video_ids or not self._api_key:
            return {}

        url = "https://www.googleapis.com/youtube/v3/videos?" + urlencode(
            {
                "part": "snippet,contentDetails",
                "id": ",".join(video_ids),
                "key": self._api_key,
                "maxResults": len(video_ids),
                "hl": "ko",
            }
        )

        try:
            with urlopen(url, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (URLError, TimeoutError, json.JSONDecodeError, OSError):
            return {}

        items = payload.get("items", []) if isinstance(payload, dict) else []
        if not isinstance(items, list):
            return {}

        metadata_by_id: dict[str, dict[str, Any]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            video_id = str(item.get("id", "")).strip()
            if video_id:
                metadata_by_id[video_id] = item

        return metadata_by_id

    def _extract_duration_seconds(self, metadata: dict[str, Any], search_item: dict[str, Any]) -> int | None:
        if isinstance(metadata, dict):
            content_details = metadata.get("contentDetails", {})
            if isinstance(content_details, dict):
                parsed = self._parse_duration_to_seconds(content_details.get("duration"))
                if parsed is not None:
                    return parsed

        parsed = self._parse_duration_to_seconds(search_item.get("duration_seconds"))
        if parsed is not None:
            return parsed
        return self._parse_duration_to_seconds(search_item.get("duration"))

    def _parse_duration_to_seconds(self, raw_duration: Any) -> int | None:
        if isinstance(raw_duration, (int, float)):
            return int(raw_duration)
        if not isinstance(raw_duration, str):
            return None

        value = raw_duration.strip().upper()
        if not value:
            return None

        if value.isdigit():
            return int(value)

        iso_match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", value)
        if iso_match:
            hours = int(iso_match.group(1) or 0)
            minutes = int(iso_match.group(2) or 0)
            seconds = int(iso_match.group(3) or 0)
            return hours * 3600 + minutes * 60 + seconds

        if ":" in value:
            parts = value.split(":")
            if len(parts) in (2, 3) and all(part.isdigit() for part in parts):
                nums = [int(part) for part in parts]
                if len(nums) == 2:
                    minutes, seconds = nums
                    return minutes * 60 + seconds
                hours, minutes, seconds = nums
                return hours * 3600 + minutes * 60 + seconds

        return None

    def _normalize_artist(self, artist: str) -> str:
        cleaned = unescape((artist or "").strip())
        if cleaned.endswith(" - Topic"):
            return cleaned[: -len(" - Topic")].strip()
        if cleaned.endswith(" - 주제"):
            return cleaned[: -len(" - 주제")].strip()
        return cleaned
