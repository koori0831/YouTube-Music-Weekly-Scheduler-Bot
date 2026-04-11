from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from src.db.database import DatabaseManager
from src.db.repositories import DaySettingsRepository, MetaRepository, PlaylistRepository, UserStatsRepository
from src.tasks.weekly_reset import WeeklyResetTask


class DummyBot:
    async def wait_until_ready(self) -> None:
        return None


@pytest.mark.asyncio
async def test_weekly_reset_runs_only_once_on_same_sunday_and_unlocks_days():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "test.db")
        db_manager = DatabaseManager(db_path)
        await db_manager.initialize()

        playlist_repo = PlaylistRepository(db_path)
        user_stats_repo = UserStatsRepository(db_path)
        day_settings_repo = DaySettingsRepository(db_path)
        meta_repo = MetaRepository(db_path)

        await playlist_repo.insert_song("월", "title", "url", 1)
        await user_stats_repo.increment(1)
        await day_settings_repo.set_lock("월", True, 9999)

        task = WeeklyResetTask(
            bot=DummyBot(),
            playlist_repo=playlist_repo,
            user_stats_repo=user_stats_repo,
            day_settings_repo=day_settings_repo,
            meta_repo=meta_repo,
        )

        kst = ZoneInfo("Asia/Seoul")
        sunday_before = datetime(2026, 3, 8, 8, 59, tzinfo=kst)
        sunday_morning = datetime(2026, 3, 8, 9, 0, tzinfo=kst)

        before = await task.run_reset_if_needed(sunday_before)
        first = await task.run_reset_if_needed(sunday_morning)
        second = await task.run_reset_if_needed(sunday_morning)

        assert before is False
        assert first is True
        assert second is False

        monday_list = await playlist_repo.list_by_day("월")
        user_count = await user_stats_repo.get_count(1)
        monday_setting = await day_settings_repo.get("월")

        assert monday_list == []
        assert user_count == 0
        assert monday_setting.is_locked is False
        assert monday_setting.exclusive_user_id is None

