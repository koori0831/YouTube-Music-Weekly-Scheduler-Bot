from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

import pytest
import pytest_asyncio

from src.constants import (
    DAY_FULL_MESSAGE,
    EXCLUSIVE_ONLY_MESSAGE,
    LOCKED_MESSAGE,
    PAST_DAY_MESSAGE,
    WEEKLY_DUPLICATE_SONG_MESSAGE,
    WEEKLY_LIMIT_MESSAGE,
)
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

        now_box = {"value": datetime(2026, 3, 8, 10, 0, 0)}  # Sunday 10:00

        def now_provider() -> datetime:
            return now_box["value"]

        service = PlaylistService(
            db_path=db_path,
            playlist_repo=playlist_repo,
            day_settings_repo=day_settings_repo,
            user_stats_repo=user_stats_repo,
            now_provider=now_provider,
        )

        yield {
            "db_path": db_path,
            "playlist_repo": playlist_repo,
            "day_settings_repo": day_settings_repo,
            "user_stats_repo": user_stats_repo,
            "meta_repo": meta_repo,
            "service": service,
            "now_box": now_box,
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
    assert validation.message is not None
    assert LOCKED_MESSAGE in validation.message
    assert "신청 가능 요일:" in validation.message
    assert "잠금(상점 사용):" in validation.message
    assert "플리 꽉참:" in validation.message


@pytest.mark.asyncio
async def test_exclusive_user_bypasses_weekly_limit(app_ctx):
    service = app_ctx["service"]
    day_settings_repo = app_ctx["day_settings_repo"]

    exclusive_user_id = 9001
    outsider_user_id = 9002
    await day_settings_repo.set_lock("월", True, exclusive_user_id)

    outsider_validation = await service.validate_request(outsider_user_id, "월")
    assert outsider_validation.allowed is False
    assert outsider_validation.message is not None
    assert EXCLUSIVE_ONLY_MESSAGE in outsider_validation.message

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


@pytest.mark.asyncio
async def test_validate_request_blocks_past_day_by_server_weekday(app_ctx):
    service = app_ctx["service"]
    now_box = app_ctx["now_box"]
    now_box["value"] = datetime(2026, 3, 4, 10, 0, 0)  # Wednesday

    validation = await service.validate_request(7777, "화")

    assert validation.allowed is False
    assert validation.message is not None
    assert PAST_DAY_MESSAGE in validation.message
    assert "서버 현재 요일: 수요일" in validation.message
    assert "신청 가능 요일: 목요일, 금요일" in validation.message


@pytest.mark.asyncio
async def test_register_song_blocks_past_day_by_server_weekday(app_ctx):
    service = app_ctx["service"]
    now_box = app_ctx["now_box"]
    now_box["value"] = datetime(2026, 3, 5, 10, 0, 0)  # Thursday

    result = await service.register_song(8888, "월", "song", "url")

    assert result.success is False
    assert PAST_DAY_MESSAGE in result.message
    assert "서버 현재 요일: 목요일" in result.message
    assert "신청 가능 요일: 금요일" in result.message


@pytest.mark.asyncio
async def test_after_midnight_current_day_is_closed(app_ctx):
    service = app_ctx["service"]
    now_box = app_ctx["now_box"]
    now_box["value"] = datetime(2026, 3, 4, 0, 30, 0)  # Wednesday 00:30

    validation = await service.validate_request(9991, "수")

    assert validation.allowed is False
    assert validation.message is not None
    assert "신청 가능 요일: 목요일, 금요일" in validation.message


@pytest.mark.asyncio
async def test_after_sunday_reset_time_all_weekdays_are_open(app_ctx):
    service = app_ctx["service"]
    now_box = app_ctx["now_box"]
    now_box["value"] = datetime(2026, 3, 8, 10, 0, 0)  # Sunday 10:00

    for day in ["월", "화", "수", "목", "금"]:
        validation = await service.validate_request(9992, day)
        assert validation.allowed is True


@pytest.mark.asyncio
async def test_sunday_after_2340_blocks_monday_playlist(app_ctx):
    service = app_ctx["service"]
    now_box = app_ctx["now_box"]
    now_box["value"] = datetime(2026, 3, 8, 23, 45, 0)  # Sunday 23:45

    validation = await service.validate_request(9996, "월")

    assert validation.allowed is False
    assert validation.message is not None
    assert "신청 가능 요일: 화요일, 수요일, 목요일, 금요일" in validation.message


@pytest.mark.asyncio
async def test_past_day_message_includes_next_week_notice_on_friday(app_ctx):
    service = app_ctx["service"]
    now_box = app_ctx["now_box"]
    now_box["value"] = datetime(2026, 3, 6, 4, 0, 0)  # Friday 04:00

    validation = await service.validate_request(9993, "목")

    assert validation.allowed is False
    assert validation.message is not None
    assert (
        "익일 신청은 전날 23:40까지 가능합니다. 금요일~일요일 08:59에는 신청이 닫히며, "
        "일요일 09:00부터 다시 신청 가능합니다."
    ) in validation.message


@pytest.mark.asyncio
async def test_denied_message_shows_no_available_days_when_none(app_ctx):
    service = app_ctx["service"]
    day_settings_repo = app_ctx["day_settings_repo"]
    now_box = app_ctx["now_box"]
    now_box["value"] = datetime(2026, 3, 4, 10, 0, 0)  # Wednesday

    await day_settings_repo.set_lock("목", True, None)
    await day_settings_repo.set_lock("금", True, None)

    validation = await service.validate_request(9994, "화")

    assert validation.allowed is False
    assert validation.message is not None
    assert "신청 가능 요일: 없음" in validation.message
    assert "현재 신청 가능한 요일이 없습니다." in validation.message


@pytest.mark.asyncio
async def test_thursday_after_2340_blocks_friday_playlist(app_ctx):
    service = app_ctx["service"]
    now_box = app_ctx["now_box"]
    now_box["value"] = datetime(2026, 3, 5, 23, 46, 0)  # Thursday 23:46

    validation = await service.validate_request(9995, "금")

    assert validation.allowed is False
    assert validation.message is not None
    assert "신청 가능 요일: 없음" in validation.message


@pytest.mark.asyncio
async def test_user_stats_decrement_restores_count_and_cleans_zero_row(app_ctx):
    user_stats_repo = app_ctx["user_stats_repo"]
    user_id = 4321

    await user_stats_repo.increment(user_id)
    await user_stats_repo.increment(user_id)
    assert await user_stats_repo.get_count(user_id) == 2

    await user_stats_repo.decrement(user_id)
    assert await user_stats_repo.get_count(user_id) == 1

    await user_stats_repo.decrement(user_id)
    assert await user_stats_repo.get_count(user_id) == 0


@pytest.mark.asyncio
async def test_register_song_blocks_duplicate_video_id_within_week(app_ctx):
    service = app_ctx["service"]

    first = await service.register_song(
        1001,
        "월",
        "song1",
        "https://www.youtube.com/watch?v=abc123XYZ00",
    )
    second = await service.register_song(
        1002,
        "화",
        "song2",
        "https://www.youtube.com/watch?v=abc123XYZ00",
    )

    assert first.success is True
    assert second.success is False
    assert WEEKLY_DUPLICATE_SONG_MESSAGE in second.message


@pytest.mark.asyncio
async def test_register_song_blocks_duplicate_video_id_across_url_formats(app_ctx):
    service = app_ctx["service"]

    first = await service.register_song(
        1001,
        "월",
        "song1",
        "https://youtu.be/QWERTY12345?t=5",
    )
    second = await service.register_song(
        1002,
        "수",
        "song2",
        "https://www.youtube.com/watch?v=QWERTY12345&list=PL123",
    )

    assert first.success is True
    assert second.success is False
    assert WEEKLY_DUPLICATE_SONG_MESSAGE in second.message


