from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from src.db.database import DatabaseManager
from src.db.repositories import MetaRepository, PlaylistRepository, UserStatsRepository
from src.tasks.weekly_reset import WeeklyResetTask


class DummyBot:
    async def wait_until_ready(self) -> None:
        return None


@pytest.mark.asyncio
async def test_weekly_reset_runs_only_once_on_same_sunday():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "test.db")
        db_manager = DatabaseManager(db_path)
        await db_manager.initialize()

        playlist_repo = PlaylistRepository(db_path)
        user_stats_repo = UserStatsRepository(db_path)
        meta_repo = MetaRepository(db_path)

        await playlist_repo.insert_song("월", "title", "url", 1)
        await user_stats_repo.increment(1)

        task = WeeklyResetTask(
            bot=DummyBot(),
            playlist_repo=playlist_repo,
            user_stats_repo=user_stats_repo,
            meta_repo=meta_repo,
        )

        kst = ZoneInfo("Asia/Seoul")
        sunday_morning = datetime(2026, 3, 8, 9, 0, tzinfo=kst)

        first = await task.run_reset_if_needed(sunday_morning)
        second = await task.run_reset_if_needed(sunday_morning)

        assert first is True
        assert second is False

        monday_list = await playlist_repo.list_by_day("월")
        user_count = await user_stats_repo.get_count(1)
        assert monday_list == []
        assert user_count == 0
