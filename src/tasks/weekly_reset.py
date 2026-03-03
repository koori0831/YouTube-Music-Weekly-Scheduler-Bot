from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

import discord
from discord.ext import tasks

from src.constants import RESET_META_KEY
from src.db.repositories import MetaRepository, PlaylistRepository, UserStatsRepository


class WeeklyResetTask:
    def __init__(
        self,
        bot: discord.Client,
        playlist_repo: PlaylistRepository,
        user_stats_repo: UserStatsRepository,
        meta_repo: MetaRepository,
    ) -> None:
        self._bot = bot
        self._playlist_repo = playlist_repo
        self._user_stats_repo = user_stats_repo
        self._meta_repo = meta_repo
        self._tz = ZoneInfo("Asia/Seoul")

    def start(self) -> None:
        if not self.weekly_reset_loop.is_running():
            self.weekly_reset_loop.start()

    def stop(self) -> None:
        if self.weekly_reset_loop.is_running():
            self.weekly_reset_loop.cancel()

    async def run_reset_if_needed(self, now: datetime | None = None) -> bool:
        current = now or datetime.now(self._tz)
        current = current.astimezone(self._tz)

        if current.weekday() != 6:
            return False

        today = current.date().isoformat()
        last_reset_date = await self._meta_repo.get(RESET_META_KEY)
        if last_reset_date == today:
            return False

        await self._playlist_repo.clear_all()
        await self._user_stats_repo.reset_all()
        await self._meta_repo.set(RESET_META_KEY, today)
        print(f"[WeeklyResetTask] Reset completed at {current.isoformat()}")
        return True

    @tasks.loop(time=time(hour=9, minute=0, tzinfo=ZoneInfo("Asia/Seoul")))
    async def weekly_reset_loop(self) -> None:
        try:
            await self.run_reset_if_needed()
        except Exception as exc:
            print(f"[WeeklyResetTask] Reset failed: {exc}")

    @weekly_reset_loop.before_loop
    async def before_weekly_reset_loop(self) -> None:
        await self._bot.wait_until_ready()
