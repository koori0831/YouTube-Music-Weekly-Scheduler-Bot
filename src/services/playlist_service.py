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

    def _is_after_friday_cutoff(self, current: datetime) -> bool:
        return current.weekday() == 4 and (current.hour, current.minute) >= (0, 40)

    def _get_available_days(self, current: datetime, logical_weekday: int) -> list[str]:
        if current.weekday() == 6 and current.hour >= 9:
            return DAY_CHOICES.copy()
        if logical_weekday >= 5:
            return DAY_CHOICES.copy()
        return DAY_CHOICES[logical_weekday:]

    def _weekday_label(self, weekday_index: int) -> str:
        weekday_names = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
        return weekday_names[weekday_index]

    def _day_list_text(self, days: list[str]) -> str:
        if not days:
            return "없음"
        return ", ".join(f"{day}요일" for day in days)

    async def _build_availability_table(self, user_id: int) -> str:
        current = self._now_provider()
        shifted = current - timedelta(minutes=40)
        logical_weekday = shifted.weekday()
        time_allowed_days = set(self._get_available_days(current, logical_weekday))

        available_days: list[str] = []
        locked_days: list[str] = []
        full_days: list[str] = []

        for target_day in DAY_CHOICES:
            day_setting = await self._day_settings_repo.get(target_day)
            day_count = await self._playlist_repo.count_by_day(target_day)
            is_full = day_count >= MAX_SONGS_PER_DAY
            is_locked_for_user = day_setting.is_locked and day_setting.exclusive_user_id != user_id

            if is_locked_for_user:
                locked_days.append(target_day)
            if is_full:
                full_days.append(target_day)

            if target_day not in time_allowed_days:
                continue
            if is_locked_for_user or is_full:
                continue
            available_days.append(target_day)

        lines = [
            f"📅 서버 현재 요일: {self._weekday_label(current.weekday())}",
            f"✅ 신청 가능 요일: {self._day_list_text(available_days)}",
            f"🔒 잠금(상점 사용): {self._day_list_text(locked_days)}",
            f"📦 플리 꽉참: {self._day_list_text(full_days)}",
        ]
        if not available_days:
            lines.append("⚠️ 현재 신청 가능한 요일이 없습니다.")
        if self._is_after_friday_cutoff(current):
            lines.append("🕘 금요일 00:40 이후에는 곡 신청이 잠기며, 일요일 09:00부터 다시 신청 가능합니다.")
        return "\n".join(lines)

    async def _build_denied_message(self, reason: str, user_id: int) -> str:
        table = await self._build_availability_table(user_id)
        return f"{reason}\n\n{table}"

    def _is_past_day(self, day: str) -> bool:
        current = self._now_provider()

        # Weekly reset runs at Sunday 09:00. After reset, all weekday playlists are open.
        if current.weekday() == 6 and current.hour >= 9:
            return False

        shifted = current - timedelta(minutes=40)
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
            message = await self._build_denied_message(PAST_DAY_MESSAGE, user_id)
            return ValidationResult(allowed=False, message=message)

        day_setting = await self._day_settings_repo.get(day)
        bypass_weekly_limit = False

        if day_setting.is_locked:
            if day_setting.exclusive_user_id is None:
                message = await self._build_denied_message(LOCKED_MESSAGE, user_id)
                return ValidationResult(allowed=False, message=message)
            if day_setting.exclusive_user_id != user_id:
                message = await self._build_denied_message(EXCLUSIVE_ONLY_MESSAGE, user_id)
                return ValidationResult(allowed=False, message=message)
            bypass_weekly_limit = True

        day_count = await self._playlist_repo.count_by_day(day)
        if day_count >= MAX_SONGS_PER_DAY:
            message = await self._build_denied_message(DAY_FULL_MESSAGE, user_id)
            return ValidationResult(allowed=False, message=message)

        weekly_count = await self._user_stats_repo.get_count(user_id)
        if (not bypass_weekly_limit) and weekly_count >= MAX_WEEKLY_SONGS_PER_USER:
            message = await self._build_denied_message(WEEKLY_LIMIT_MESSAGE, user_id)
            return ValidationResult(allowed=False, message=message)

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
            message = await self._build_denied_message(PAST_DAY_MESSAGE, user_id)
            return RegisterResult(False, message, [])

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
