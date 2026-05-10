from __future__ import annotations

import asyncio
import json
import logging
import re
from html import unescape
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from ytmusicapi import YTMusic

from src.models import YouTubeResult

logger = logging.getLogger(__name__)


class YouTubeService:
    def __init__(self, api_key: str | None = None) -> None:
        # ytmusicapi public search does not require API key.
        self._service = YTMusic(language="ko", location="KR")
        self._api_key = api_key

    async def search_music(self, query: str, limit: int = 3) -> list[YouTubeResult]:
        return await asyncio.to_thread(self._search_music_sync, query, limit)

    def _create_service(self) -> YTMusic:
        return YTMusic(language="ko", location="KR")

    def _search_music_sync(self, query: str, limit: int) -> list[YouTubeResult]:
        errors: list[str] = []

        direct_results = self._search_with_fallback(
            service=self._service,
            query=query,
            limit=limit,
            errors=errors,
            source="shared-direct",
        )
        if direct_results:
            return direct_results

        fresh_results = self._search_with_fallback(
            service=self._create_service(),
            query=query,
            limit=limit,
            errors=errors,
            source="fresh-direct",
        )
        if fresh_results:
            return fresh_results

        if errors:
            logger.warning("YouTube search failed for query=%r: %s", query, " | ".join(errors))
        return []

    def _search_with_fallback(
        self,
        service: YTMusic,
        query: str,
        limit: int,
        errors: list[str],
        source: str,
    ) -> list[YouTubeResult]:
        try:
            return self._search_music_with_service(service, query, limit)
        except Exception as exc:
            errors.append(f"{source}: {self._describe_search_error(exc)}")
            return []

    def _describe_search_error(self, exc: Exception) -> str:
        lowered = str(exc).lower()
        exc_type = exc.__class__.__name__

        if isinstance(exc, TimeoutError):
            reason = "timeout"
        elif isinstance(exc, URLError):
            reason = "url_error"
        elif "connect timeout" in lowered:
            reason = "connect_timeout"
        elif "connection refused" in lowered:
            reason = "connection_refused"
        elif "name or service not known" in lowered or "nodename nor servname provided" in lowered:
            reason = "dns_error"
        else:
            reason = "request_failed"

        return f"{reason} ({exc_type}): {exc}"

    def _search_music_with_service(self, service: YTMusic, query: str, limit: int) -> list[YouTubeResult]:
        primary_items = service.search(query, filter="songs", limit=limit)

        fallback_items: list[dict[str, Any]] = []
        if len(primary_items) < limit:
            fallback_items = service.search(query, filter="videos", limit=limit * 2)

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
                    or "?쒕ぉ ?놁쓬"
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
                normalized_channel_title = self._normalize_artist(channel_title)
                description_artist = self._extract_artist_from_auto_generated_description(
                    snippet.get("description"),
                    snippet.get("title") or search_item.get("title"),
                )
                if normalized_channel_title.lower() == "release" and description_artist:
                    return description_artist
                return normalized_channel_title

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

    def _extract_artist_from_auto_generated_description(self, description: Any, title: Any) -> str | None:
        if not isinstance(description, str):
            return None

        lines = [unescape(line.strip()) for line in description.splitlines()]
        lines = [line for line in lines if line]
        if not lines or not lines[0].startswith("Provided to YouTube by "):
            return None

        clean_title = unescape(str(title or "")).strip()
        for line in lines[1:]:
            if " · " not in line:
                continue

            parts = [part.strip() for part in line.split(" · ") if part.strip()]
            if len(parts) < 2:
                continue
            maybe_title = parts[0]
            if clean_title and maybe_title != clean_title:
                continue
            return self._normalize_artist(parts[1])

        return None
