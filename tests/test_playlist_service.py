from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

from src.constants import DAY_FULL_MESSAGE, EXCLUSIVE_ONLY_MESSAGE, LOCKED_MESSAGE, WEEKLY_LIMIT_MESSAGE
from src.db.database import DatabaseManager
from src.db.repositories import (
    DaySettingsRepository,
    MetaRepository,
    PlaylistRepository,
    UserStatsRepository,
)
from src.services.playlist_service import PlaylistService


@pytest_asyncio.fixture()
async def app_ctx():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "test.db")
        db_manager = DatabaseManager(db_path)
        await db_manager.initialize()

        playlist_repo = PlaylistRepository(db_path)
        day_settings_repo = DaySettingsRepository(db_path)
        user_stats_repo = UserStatsRepository(db_path)
        meta_repo = MetaRepository(db_path)
        service = PlaylistService(
            db_path=db_path,
            playlist_repo=playlist_repo,
            day_settings_repo=day_settings_repo,
            user_stats_repo=user_stats_repo,
        )

        yield {
            "db_path": db_path,
            "playlist_repo": playlist_repo,
            "day_settings_repo": day_settings_repo,
            "user_stats_repo": user_stats_repo,
            "meta_repo": meta_repo,
            "service": service,
        }


@pytest.mark.asyncio
async def test_weekly_limit_for_normal_user(app_ctx):
    service = app_ctx["service"]

    r1 = await service.register_song(1001, "월", "song1", "url1")
    r2 = await service.register_song(1001, "화", "song2", "url2")
    r3 = await service.register_song(1001, "수", "song3", "url3")

    assert r1.success is True
    assert r2.success is True
    assert r3.success is False
    assert r3.message == WEEKLY_LIMIT_MESSAGE


@pytest.mark.asyncio
async def test_day_full_limit_boundary(app_ctx):
    service = app_ctx["service"]
    playlist_repo = app_ctx["playlist_repo"]

    for i in range(11):
        await playlist_repo.insert_song("목", f"seed-{i}", f"seed-url-{i}", 2000 + i)

    r12 = await service.register_song(3001, "목", "song12", "url12")
    r13 = await service.register_song(3002, "목", "song13", "url13")

    assert r12.success is True
    assert r13.success is False
    assert r13.message == DAY_FULL_MESSAGE


@pytest.mark.asyncio
async def test_locked_without_exclusive_blocks_everyone(app_ctx):
    service = app_ctx["service"]
    day_settings_repo = app_ctx["day_settings_repo"]

    await day_settings_repo.set_lock("금", True, None)
    validation = await service.validate_request(5001, "금")

    assert validation.allowed is False
    assert validation.message == LOCKED_MESSAGE


@pytest.mark.asyncio
async def test_exclusive_user_bypasses_weekly_limit(app_ctx):
    service = app_ctx["service"]
    day_settings_repo = app_ctx["day_settings_repo"]

    exclusive_user_id = 9001
    outsider_user_id = 9002
    await day_settings_repo.set_lock("월", True, exclusive_user_id)

    outsider_validation = await service.validate_request(outsider_user_id, "월")
    assert outsider_validation.allowed is False
    assert outsider_validation.message == EXCLUSIVE_ONLY_MESSAGE

    r1 = await service.register_song(exclusive_user_id, "월", "a", "u1")
    r2 = await service.register_song(exclusive_user_id, "월", "b", "u2")
    r3 = await service.register_song(exclusive_user_id, "월", "c", "u3")

    assert r1.success is True
    assert r2.success is True
    assert r3.success is True


@pytest.mark.asyncio
async def test_unlock_restores_normal_limit_rule(app_ctx):
    service = app_ctx["service"]
    day_settings_repo = app_ctx["day_settings_repo"]

    user_id = 7001
    await day_settings_repo.set_lock("화", True, user_id)
    assert (await service.register_song(user_id, "화", "a", "u1")).success is True
    assert (await service.register_song(user_id, "화", "b", "u2")).success is True

    await day_settings_repo.set_lock("화", False, None)
    r1 = await service.register_song(user_id, "수", "c", "u3")
    r2 = await service.register_song(user_id, "목", "d", "u4")
    r3 = await service.register_song(user_id, "금", "e", "u5")

    assert r1.success is True
    assert r2.success is True
    assert r3.success is False
    assert r3.message == WEEKLY_LIMIT_MESSAGE


@pytest.mark.asyncio
async def test_lock_day_clears_existing_songs_and_rebuilds_stats(app_ctx):
    playlist_repo = app_ctx["playlist_repo"]
    user_stats_repo = app_ctx["user_stats_repo"]
    day_settings_repo = app_ctx["day_settings_repo"]

    await playlist_repo.insert_song("월", "m1", "u1", 1)
    await playlist_repo.insert_song("월", "m2", "u2", 2)
    await playlist_repo.insert_song("화", "t1", "u3", 1)
    await user_stats_repo.rebuild_from_playlists()

    assert await user_stats_repo.get_count(1) == 2
    assert await user_stats_repo.get_count(2) == 1

    await day_settings_repo.set_lock("월", True, None)
    deleted = await playlist_repo.clear_by_day("월")
    await user_stats_repo.rebuild_from_playlists()

    assert deleted == 2
    assert await playlist_repo.list_by_day("월") == []
    assert await user_stats_repo.get_count(1) == 1
    assert await user_stats_repo.get_count(2) == 0


@pytest.mark.asyncio
async def test_reset_all_repositories_restore_initial_state(app_ctx):
    playlist_repo = app_ctx["playlist_repo"]
    user_stats_repo = app_ctx["user_stats_repo"]
    day_settings_repo = app_ctx["day_settings_repo"]
    meta_repo = app_ctx["meta_repo"]

    await playlist_repo.insert_song("월", "m1", "u1", 1)
    await user_stats_repo.increment(1)
    await day_settings_repo.set_lock("월", True, 9999)
    await meta_repo.set("last_weekly_reset_date", "2026-03-03")

    await playlist_repo.clear_all()
    await user_stats_repo.reset_all()
    await day_settings_repo.reset_all()
    await meta_repo.clear_all()

    assert await playlist_repo.list_by_day("월") == []
    assert await user_stats_repo.get_count(1) == 0
    monday = await day_settings_repo.get("월")
    assert monday.is_locked is False
    assert monday.exclusive_user_id is None
    assert await meta_repo.get("last_weekly_reset_date") is None
