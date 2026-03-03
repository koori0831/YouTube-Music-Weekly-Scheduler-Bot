from __future__ import annotations

import aiosqlite

from src.constants import DAY_CHOICES


class DatabaseManager:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    @property
    def db_path(self) -> str:
        return self._db_path

    async def initialize(self) -> None:
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS playlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    day_of_week TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    user_id INTEGER NOT NULL
                )
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_playlists_day
                ON playlists(day_of_week)
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_playlists_user
                ON playlists(user_id)
                """
            )

            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS day_settings (
                    day_of_week TEXT PRIMARY KEY,
                    is_locked INTEGER NOT NULL DEFAULT 0,
                    exclusive_user_id INTEGER NULL
                )
                """
            )

            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_stats (
                    user_id INTEGER PRIMARY KEY,
                    weekly_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )

            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )

            for day in DAY_CHOICES:
                await conn.execute(
                    """
                    INSERT OR IGNORE INTO day_settings (day_of_week, is_locked, exclusive_user_id)
                    VALUES (?, 0, NULL)
                    """,
                    (day,),
                )

            await conn.commit()
