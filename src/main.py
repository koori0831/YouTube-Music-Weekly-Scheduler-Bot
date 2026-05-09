from __future__ import annotations

import asyncio

import discord
from discord.ext import commands

from src.cogs.music_cog import setup as setup_music_cog
from src.config import ConfigError, Settings, load_settings
from src.db.database import DatabaseManager
from src.db.repositories import (
    DaySettingsRepository,
    MetaRepository,
    PlaylistRepository,
    UserStatsRepository,
)
from src.services.playlist_service import PlaylistService
from src.services.youtube_service import YouTubeService
from src.tasks.playlist_close_announcement import PlaylistCloseAnnouncementTask
from src.tasks.weekly_reset import WeeklyResetTask


class MusicSchedulerBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.settings = settings

        self.db_manager = DatabaseManager(settings.db_path)
        self.playlist_repo = PlaylistRepository(settings.db_path)
        self.day_settings_repo = DaySettingsRepository(settings.db_path)
        self.user_stats_repo = UserStatsRepository(settings.db_path)
        self.meta_repo = MetaRepository(settings.db_path)

        self.playlist_service = PlaylistService(
            db_path=settings.db_path,
            playlist_repo=self.playlist_repo,
            day_settings_repo=self.day_settings_repo,
            user_stats_repo=self.user_stats_repo,
        )
        self.youtube_service = YouTubeService(settings.youtube_api_key)
        self.weekly_reset_task: WeeklyResetTask | None = None
        self.playlist_close_announcement_task: PlaylistCloseAnnouncementTask | None = None

    async def setup_hook(self) -> None:
        await self.db_manager.initialize()

        await setup_music_cog(
            bot=self,
            playlist_service=self.playlist_service,
            playlist_repo=self.playlist_repo,
            day_settings_repo=self.day_settings_repo,
            user_stats_repo=self.user_stats_repo,
            meta_repo=self.meta_repo,
            youtube_service=self.youtube_service,
        )

        if self.settings.discord_guild_id:
            guild = discord.Object(id=self.settings.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            print(f"Synced slash commands to guild {self.settings.discord_guild_id}")
        else:
            await self.tree.sync()
            print("Synced global slash commands")

        self.weekly_reset_task = WeeklyResetTask(
            bot=self,
            playlist_repo=self.playlist_repo,
            user_stats_repo=self.user_stats_repo,
            day_settings_repo=self.day_settings_repo,
            meta_repo=self.meta_repo,
        )
        await self.weekly_reset_task.run_reset_if_needed()
        self.weekly_reset_task.start()

        self.playlist_close_announcement_task = PlaylistCloseAnnouncementTask(
            bot=self,
            playlist_repo=self.playlist_repo,
            day_settings_repo=self.day_settings_repo,
            meta_repo=self.meta_repo,
            request_channel_id=self.settings.song_request_channel_id,
            announcement_channel_id=self.settings.song_announcement_channel_id,
        )
        await self.playlist_close_announcement_task.run_close_announcement_if_needed()
        self.playlist_close_announcement_task.start()

    async def close(self) -> None:
        if self.weekly_reset_task:
            self.weekly_reset_task.stop()
        if self.playlist_close_announcement_task:
            self.playlist_close_announcement_task.stop()
        await super().close()

    async def on_ready(self) -> None:
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.competing,
                name="/도움말 입력하기!",
            )
        )
        print(f"Logged in as {self.user} (ID: {self.user.id})")


async def _run() -> None:
    settings = load_settings()
    bot = MusicSchedulerBot(settings)
    await bot.start(settings.discord_bot_token)


def main() -> None:
    try:
        asyncio.run(_run())
    except ConfigError as exc:
        print(f"Configuration error: {exc}")


if __name__ == "__main__":
    main()

