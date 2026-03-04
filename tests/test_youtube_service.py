from __future__ import annotations

from src.services import youtube_service


class _FakeYTMusic:
    def __init__(self, items: list[dict], fallback_items: list[dict] | None = None) -> None:
        self._items = items
        self._fallback_items = fallback_items or []

    def search(self, query: str, filter: str, limit: int) -> list[dict]:
        if filter == "songs":
            return self._items[:limit]
        if filter == "videos":
            return self._fallback_items[:limit]
        return []


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def test_search_music_uses_data_api_metadata_and_strips_topic(monkeypatch):
    fake = _FakeYTMusic(
        items=[
            {
                "videoId": "abc123",
                "title": "fallback title",
                "artists": [{"name": "fallback artist"}],
                "thumbnails": [{"url": "https://img/fallback.jpg"}],
            }
        ]
    )
    monkeypatch.setattr(youtube_service, "YTMusic", lambda *args, **kwargs: fake)

    svc = youtube_service.YouTubeService(api_key="key")
    monkeypatch.setattr(
        svc,
        "_fetch_video_metadata",
        lambda ids: {
            "abc123": {
                "id": "abc123",
                "snippet": {
                    "title": "real title",
                    "channelTitle": "real artist - Topic",
                    "thumbnails": {
                        "default": {"url": "https://img/small.jpg", "width": 120, "height": 90},
                        "high": {"url": "https://img/big.jpg", "width": 480, "height": 360},
                    },
                },
                "contentDetails": {"duration": "PT4M31S"},
            }
        },
    )

    results = svc._search_music_sync("q", 1)

    assert len(results) == 1
    assert results[0].title == "real title"
    assert results[0].artist == "real artist"
    assert results[0].thumbnail_url == "https://img/big.jpg"
    assert results[0].duration_seconds == 271


def test_search_music_falls_back_to_search_fields_when_metadata_missing(monkeypatch):
    fake = _FakeYTMusic(
        items=[
            {
                "videoId": "abc123",
                "title": "fallback title",
                "artists": [{"name": "fallback artist - Topic"}],
                "thumbnails": [{"url": "https://img/fallback.jpg"}],
                "duration": "4:29",
            }
        ]
    )
    monkeypatch.setattr(youtube_service, "YTMusic", lambda *args, **kwargs: fake)

    svc = youtube_service.YouTubeService(api_key="key")
    monkeypatch.setattr(svc, "_fetch_video_metadata", lambda ids: {})

    results = svc._search_music_sync("q", 1)

    assert len(results) == 1
    assert results[0].title == "fallback title"
    assert results[0].artist == "fallback artist"
    assert results[0].thumbnail_url == "https://img/fallback.jpg"
    assert results[0].duration_seconds == 269


def test_fetch_video_metadata_parses_items(monkeypatch):
    fake = _FakeYTMusic(items=[])
    monkeypatch.setattr(youtube_service, "YTMusic", lambda *args, **kwargs: fake)

    payload = b'{"items":[{"id":"vid1","snippet":{"title":"t"}}]}'
    monkeypatch.setattr(youtube_service, "urlopen", lambda *args, **kwargs: _FakeResponse(payload))

    svc = youtube_service.YouTubeService(api_key="key")
    metadata = svc._fetch_video_metadata(["vid1"])

    assert "vid1" in metadata
    assert metadata["vid1"]["snippet"]["title"] == "t"
