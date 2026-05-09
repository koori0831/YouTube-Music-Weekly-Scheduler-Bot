from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from src.db.database import DatabaseManager
from src.db.repositories import DaySettingsRepository, MetaRepository, PlaylistRepository
from src.tasks.playlist_close_announcement import PlaylistCloseAnnouncementTask


class FakeMessage:
    def __init__(self, content=None, embeds=None) -> None:
        self.content = content
        self.embeds = embeds or []

    async def forward(self, destination) -> None:
        await destination.send(content=self.content, embeds=self.embeds)


class FakeChannel:
    def __init__(self) -> None:
        self.messages = []

    async def send(self, content=None, embed=None, embeds=None):
        message_embeds = embeds if embeds is not None else ([embed] if embed is not None else [])
        message = FakeMessage(content=content, embeds=message_embeds)
        self.messages.append(message)
        return message


class FakeBot:
    def __init__(self, channels) -> None:
        self.channels = channels

    def get_channel(self, channel_id: int):
        return self.channels.get(channel_id)

    async def fetch_channel(self, channel_id: int):
        return self.channels[channel_id]

    async def wait_until_ready(self) -> None:
        return None


@pytest.mark.asyncio
async def test_close_announcement_sends_shuffle_to_request_and_forwards_to_announcement():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "test.db")
        await DatabaseManager(db_path).initialize()
        playlist_repo = PlaylistRepository(db_path)
        day_settings_repo = DaySettingsRepository(db_path)
        meta_repo = MetaRepository(db_path)
        await playlist_repo.insert_song("화", "song-a", "url-a", 1)
        await playlist_repo.insert_song("화", "song-b", "url-b", 2)

        request_channel = FakeChannel()
        announcement_channel = FakeChannel()
        task = PlaylistCloseAnnouncementTask(
            bot=FakeBot({1: request_channel, 2: announcement_channel}),
            playlist_repo=playlist_repo,
            day_settings_repo=day_settings_repo,
            meta_repo=meta_repo,
            request_channel_id=1,
            announcement_channel_id=2,
        )

        kst = ZoneInfo("Asia/Seoul")
        sent = await task.run_close_announcement_if_needed(datetime(2026, 5, 4, 23, 40, tzinfo=kst))
        sent_again = await task.run_close_announcement_if_needed(
            datetime(2026, 5, 4, 23, 41, tzinfo=kst)
        )

        assert sent is True
        assert sent_again is False
        assert len(request_channel.messages) == 1
        assert len(announcement_channel.messages) == 1
        assert request_channel.messages[0].embeds[0].title == "🔀 화요일 셔플 결과"
        assert announcement_channel.messages[0].embeds[0].title == "🔀 화요일 셔플 결과"


@pytest.mark.asyncio
async def test_close_announcement_locked_owner_posts_view_to_announcement_only():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "test.db")
        await DatabaseManager(db_path).initialize()
        playlist_repo = PlaylistRepository(db_path)
        day_settings_repo = DaySettingsRepository(db_path)
        meta_repo = MetaRepository(db_path)
        await playlist_repo.insert_song("화", "owner-song", "url", 1234)
        await day_settings_repo.set_lock("화", True, 1234)

        request_channel = FakeChannel()
        announcement_channel = FakeChannel()
        task = PlaylistCloseAnnouncementTask(
            bot=FakeBot({1: request_channel, 2: announcement_channel}),
            playlist_repo=playlist_repo,
            day_settings_repo=day_settings_repo,
            meta_repo=meta_repo,
            request_channel_id=1,
            announcement_channel_id=2,
        )

        kst = ZoneInfo("Asia/Seoul")
        sent = await task.run_close_announcement_if_needed(datetime(2026, 5, 4, 23, 40, tzinfo=kst))

        assert sent is True
        assert request_channel.messages == []
        assert len(announcement_channel.messages) == 1
        assert announcement_channel.messages[0].content == "<@1234> 상점 플리입니다."
        assert announcement_channel.messages[0].embeds[0].title == "📋 화요일 현재 현황 (1곡/12곡)"
