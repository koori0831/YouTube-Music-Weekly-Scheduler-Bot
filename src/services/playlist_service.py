from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

import aiosqlite

from src.constants import (
    DAY_CHOICES,
    DAY_FULL_MESSAGE,
    EXCLUSIVE_ONLY_MESSAGE,
    LOCKED_MESSAGE,
    MAX_SONGS_PER_DAY,
    MAX_WEEKLY_SONGS_PER_USER,
    PAST_DAY_MESSAGE,
    REGISTER_SUCCESS_MESSAGE,
    WEEKLY_LIMIT_MESSAGE,
)
from src.db.repositories import DaySettingsRepository, PlaylistRepository, UserStatsRepository
from src.models import RegisterResult, ValidationResult


class PlaylistService:
    def __init__(
        self,
        db_path: str,
        playlist_repo: PlaylistRepository,
        day_settings_repo: DaySettingsRepository,
        user_stats_repo: UserStatsRepository,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._db_path = db_path
        self._playlist_repo = playlist_repo
        self._day_settings_repo = day_settings_repo
        self._user_stats_repo = user_stats_repo
        self._now_provider = now_provider or datetime.now

    def _is_past_day(self, day: str) -> bool:
        current = self._now_provider()

        # Weekly reset runs at Sunday 09:00. After reset, all weekday playlists are open.
        if current.weekday() == 6 and current.hour >= 9:
            return False

        shifted = current - timedelta(hours=3)
        logical_weekday = shifted.weekday()

        # Logical Saturday/Sunday has no past-day restriction for weekday playlists.
        if logical_weekday >= 5:
            return False

        request_day_index = DAY_CHOICES.index(day)
        return request_day_index < logical_weekday

    async def validate_request(self, user_id: int, day: str) -> ValidationResult:
        if day not in DAY_CHOICES:
            return ValidationResult(allowed=False, message="유효하지 않은 요일입니다.")

        if self._is_past_day(day):
            return ValidationResult(allowed=False, message=PAST_DAY_MESSAGE)

        day_setting = await self._day_settings_repo.get(day)
        bypass_weekly_limit = False

        if day_setting.is_locked:
            if day_setting.exclusive_user_id is None:
                return ValidationResult(allowed=False, message=LOCKED_MESSAGE)
            if day_setting.exclusive_user_id != user_id:
                return ValidationResult(allowed=False, message=EXCLUSIVE_ONLY_MESSAGE)
            bypass_weekly_limit = True

        day_count = await self._playlist_repo.count_by_day(day)
        if day_count >= MAX_SONGS_PER_DAY:
            return ValidationResult(allowed=False, message=DAY_FULL_MESSAGE)

        weekly_count = await self._user_stats_repo.get_count(user_id)
        if (not bypass_weekly_limit) and weekly_count >= MAX_WEEKLY_SONGS_PER_USER:
            return ValidationResult(allowed=False, message=WEEKLY_LIMIT_MESSAGE)

        return ValidationResult(
            allowed=True,
            message=None,
            bypass_weekly_limit=bypass_weekly_limit,
        )

    async def register_song(
        self,
        user_id: int,
        day: str,
        title: str,
        url: str,
    ) -> RegisterResult:
        if day not in DAY_CHOICES:
            return RegisterResult(False, "유효하지 않은 요일입니다.", [])
        if self._is_past_day(day):
            return RegisterResult(False, PAST_DAY_MESSAGE, [])

        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            try:
                await conn.execute("BEGIN IMMEDIATE")

                cursor = await conn.execute(
                    """
                    SELECT is_locked, exclusive_user_id
                    FROM day_settings
                    WHERE day_of_week = ?
                    """,
                    (day,),
                )
                day_row = await cursor.fetchone()
                if day_row is None:
                    await conn.execute("ROLLBACK")
                    return RegisterResult(False, "유효하지 않은 요일입니다.", [])

                is_locked = bool(day_row["is_locked"])
                exclusive_user_id = day_row["exclusive_user_id"]

                bypass_weekly_limit = False
                if is_locked:
                    if exclusive_user_id is None:
                        await conn.execute("ROLLBACK")
                        return RegisterResult(False, LOCKED_MESSAGE, [])
                    if exclusive_user_id != user_id:
                        await conn.execute("ROLLBACK")
                        return RegisterResult(False, EXCLUSIVE_ONLY_MESSAGE, [])
                    bypass_weekly_limit = True

                cursor = await conn.execute(
                    "SELECT COUNT(*) AS c FROM playlists WHERE day_of_week = ?",
                    (day,),
                )
                count_row = await cursor.fetchone()
                day_count = int(count_row["c"]) if count_row else 0
                if day_count >= MAX_SONGS_PER_DAY:
                    await conn.execute("ROLLBACK")
                    return RegisterResult(False, DAY_FULL_MESSAGE, [])

                cursor = await conn.execute(
                    "SELECT weekly_count FROM user_stats WHERE user_id = ?",
                    (user_id,),
                )
                weekly_row = await cursor.fetchone()
                weekly_count = int(weekly_row[0]) if weekly_row else 0

                if (not bypass_weekly_limit) and weekly_count >= MAX_WEEKLY_SONGS_PER_USER:
                    await conn.execute("ROLLBACK")
                    return RegisterResult(False, WEEKLY_LIMIT_MESSAGE, [])

                await conn.execute(
                    """
                    INSERT INTO playlists(day_of_week, title, url, user_id)
                    VALUES (?, ?, ?, ?)
                    """,
                    (day, title, url, user_id),
                )

                if not bypass_weekly_limit:
                    await conn.execute(
                        """
                        INSERT INTO user_stats(user_id, weekly_count)
                        VALUES (?, 1)
                        ON CONFLICT(user_id) DO UPDATE SET weekly_count = weekly_count + 1
                        """,
                        (user_id,),
                    )

                cursor = await conn.execute(
                    """
                    SELECT title
                    FROM playlists
                    WHERE day_of_week = ?
                    ORDER BY id ASC
                    """,
                    (day,),
                )
                rows = await cursor.fetchall()
                titles = [str(row["title"]) for row in rows]

                await conn.commit()
                return RegisterResult(True, REGISTER_SUCCESS_MESSAGE, titles)
            except Exception:
                await conn.rollback()
                raise
