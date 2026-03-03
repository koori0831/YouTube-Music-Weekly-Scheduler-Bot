from __future__ import annotations

import aiosqlite

from src.constants import DAY_CHOICES
from src.models import DaySetting


class PlaylistRepository:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def count_by_day(self, day: str) -> int:
        async with aiosqlite.connect(self._db_path) as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM playlists WHERE day_of_week = ?", (day,)
            )
            row = await cursor.fetchone()
            return int(row[0]) if row else 0

    async def insert_song(self, day: str, title: str, url: str, user_id: int) -> None:
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                """
                INSERT INTO playlists(day_of_week, title, url, user_id)
                VALUES (?, ?, ?, ?)
                """,
                (day, title, url, user_id),
            )
            await conn.commit()

    async def list_by_day(self, day: str) -> list[dict[str, object]]:
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                """
                SELECT id, day_of_week, title, url, user_id
                FROM playlists
                WHERE day_of_week = ?
                ORDER BY id ASC
                """,
                (day,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def clear_all(self) -> None:
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute("DELETE FROM playlists")
            await conn.commit()

    async def clear_by_day(self, day: str) -> int:
        async with aiosqlite.connect(self._db_path) as conn:
            cursor = await conn.execute(
                "DELETE FROM playlists WHERE day_of_week = ?",
                (day,),
            )
            deleted = cursor.rowcount if cursor.rowcount is not None else 0
            await conn.commit()
            return int(deleted)


class DaySettingsRepository:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def get(self, day: str) -> DaySetting:
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                """
                SELECT day_of_week, is_locked, exclusive_user_id
                FROM day_settings
                WHERE day_of_week = ?
                """,
                (day,),
            )
            row = await cursor.fetchone()
            if row is None:
                raise ValueError(f"day_settings에 '{day}' 설정이 없습니다.")
            return DaySetting(
                day_of_week=row["day_of_week"],
                is_locked=bool(row["is_locked"]),
                exclusive_user_id=row["exclusive_user_id"],
            )

    async def set_lock(
        self,
        day: str,
        is_locked: bool,
        exclusive_user_id: int | None,
    ) -> None:
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                """
                UPDATE day_settings
                SET is_locked = ?, exclusive_user_id = ?
                WHERE day_of_week = ?
                """,
                (1 if is_locked else 0, exclusive_user_id, day),
            )
            await conn.commit()

    async def reset_all(self) -> None:
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                """
                UPDATE day_settings
                SET is_locked = 0, exclusive_user_id = NULL
                WHERE day_of_week IN (?, ?, ?, ?, ?)
                """,
                tuple(DAY_CHOICES),
            )
            await conn.commit()


class UserStatsRepository:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def get_count(self, user_id: int) -> int:
        async with aiosqlite.connect(self._db_path) as conn:
            cursor = await conn.execute(
                "SELECT weekly_count FROM user_stats WHERE user_id = ?", (user_id,)
            )
            row = await cursor.fetchone()
            return int(row[0]) if row else 0

    async def increment(self, user_id: int) -> None:
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                """
                INSERT INTO user_stats(user_id, weekly_count)
                VALUES (?, 1)
                ON CONFLICT(user_id) DO UPDATE SET weekly_count = weekly_count + 1
                """,
                (user_id,),
            )
            await conn.commit()

    async def reset_all(self) -> None:
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute("DELETE FROM user_stats")
            await conn.commit()

    async def rebuild_from_playlists(self) -> None:
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute("DELETE FROM user_stats")
            await conn.execute(
                """
                INSERT INTO user_stats(user_id, weekly_count)
                SELECT user_id, COUNT(*) as weekly_count
                FROM playlists
                GROUP BY user_id
                """
            )
            await conn.commit()


class MetaRepository:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def get(self, key: str) -> str | None:
        async with aiosqlite.connect(self._db_path) as conn:
            cursor = await conn.execute("SELECT value FROM meta WHERE key = ?", (key,))
            row = await cursor.fetchone()
            return str(row[0]) if row else None

    async def set(self, key: str, value: str) -> None:
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                """
                INSERT INTO meta(key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )
            await conn.commit()

    async def clear_all(self) -> None:
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute("DELETE FROM meta")
            await conn.commit()
