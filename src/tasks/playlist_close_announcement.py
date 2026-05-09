from __future__ import annotations

import random
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import discord
from discord.ext import tasks

from src.constants import DAY_CHOICES, get_max_songs_for_day
from src.db.repositories import DaySettingsRepository, MetaRepository, PlaylistRepository
from src.utils.response_embed import build_song_list_embed
from src.utils.song_format import format_song_display


class PlaylistCloseAnnouncementTask:
    def __init__(
        self,
        bot: discord.Client,
        playlist_repo: PlaylistRepository,
        day_settings_repo: DaySettingsRepository,
        meta_repo: MetaRepository,
        request_channel_id: int | None,
        announcement_channel_id: int | None,
    ) -> None:
        self._bot = bot
        self._playlist_repo = playlist_repo
        self._day_settings_repo = day_settings_repo
        self._meta_repo = meta_repo
        self._request_channel_id = request_channel_id
        self._announcement_channel_id = announcement_channel_id
        self._tz = ZoneInfo("Asia/Seoul")

    def start(self) -> None:
        if not self.close_announcement_loop.is_running():
            self.close_announcement_loop.start()

    def stop(self) -> None:
        if self.close_announcement_loop.is_running():
            self.close_announcement_loop.cancel()

    def _normalize_current(self, now: datetime | None) -> datetime:
        if now is None:
            return datetime.now(self._tz)
        if now.tzinfo is None:
            return now.replace(tzinfo=self._tz)
        return now.astimezone(self._tz)

    def _closed_playlist_for(self, now: datetime) -> tuple[str, str] | None:
        current = self._normalize_current(now)
        if current.time() < time(hour=23, minute=40):
            return None

        weekday = current.weekday()
        if weekday == 6:
            target_day = DAY_CHOICES[0]
        elif 0 <= weekday <= 3:
            target_day = DAY_CHOICES[weekday + 1]
        else:
            return None

        target_date = (current.date() + timedelta(days=1)).isoformat()
        return target_day, target_date

    async def _get_channel(self, channel_id: int) -> discord.abc.Messageable:
        channel = self._bot.get_channel(channel_id)
        if channel is None:
            channel = await self._bot.fetch_channel(channel_id)
        if not hasattr(channel, "send"):
            raise TypeError(f"Channel {channel_id} does not support sending messages.")
        return channel

    async def _forward_or_copy(
        self,
        message: discord.Message,
        destination: discord.abc.Messageable,
    ) -> None:
        forward = getattr(message, "forward", None)
        if forward is not None:
            try:
                await forward(destination=destination)
                return
            except TypeError:
                try:
                    await forward(destination)
                    return
                except (TypeError, discord.HTTPException):
                    pass
            except discord.HTTPException:
                pass

        await destination.send(content=message.content or None, embeds=message.embeds)

    async def _send_shuffle_and_forward(self, day: str) -> bool:
        if self._request_channel_id is None or self._announcement_channel_id is None:
            return False

        request_channel = await self._get_channel(self._request_channel_id)
        announcement_channel = await self._get_channel(self._announcement_channel_id)
        songs = await self._playlist_repo.list_by_day(day)
        if not songs:
            return False

        titles = [format_song_display(str(song["title"])) for song in songs]
        random.shuffle(titles)
        embed = build_song_list_embed(
            title=f"{day}요일 셔플 결과",
            songs=titles,
            kind="shuffle",
            empty_text=f"{day}요일 플레이리스트가 비어 있습니다.",
        )
        message = await request_channel.send(embed=embed)
        await self._forward_or_copy(message, announcement_channel)
        return True

    async def _send_locked_owner_view(self, day: str, owner_id: int) -> bool:
        if self._announcement_channel_id is None:
            return False

        announcement_channel = await self._get_channel(self._announcement_channel_id)
        songs = await self._playlist_repo.list_by_day(day)
        if not songs:
            return False

        titles = [format_song_display(str(song["title"])) for song in songs]
        embed = build_song_list_embed(
            title=f"{day}요일 현재 현황",
            songs=titles,
            kind="view",
            max_songs=get_max_songs_for_day(day),
            empty_text=f"{day}요일 플레이리스트가 비어 있습니다.",
        )
        await announcement_channel.send(content=f"<@{owner_id}> 상점 플리입니다.", embed=embed)
        return True

    async def run_close_announcement_if_needed(self, now: datetime | None = None) -> bool:
        if self._announcement_channel_id is None:
            return False

        closed_playlist = self._closed_playlist_for(self._normalize_current(now))
        if closed_playlist is None:
            return False

        day, target_date = closed_playlist
        meta_key = f"playlist_close_announcement:{target_date}:{day}"
        if await self._meta_repo.get(meta_key) == "sent":
            return False

        day_setting = await self._day_settings_repo.get(day)
        if day_setting.is_locked and day_setting.exclusive_user_id is not None:
            sent = await self._send_locked_owner_view(day, int(day_setting.exclusive_user_id))
        else:
            sent = await self._send_shuffle_and_forward(day)

        if not sent:
            return False

        await self._meta_repo.set(meta_key, "sent")
        print(f"[PlaylistCloseAnnouncementTask] Sent {day} close announcement for {target_date}")
        return True

    @tasks.loop(minutes=1)
    async def close_announcement_loop(self) -> None:
        try:
            await self.run_close_announcement_if_needed()
        except Exception as exc:
            print(f"[PlaylistCloseAnnouncementTask] Announcement failed: {exc}")

    @close_announcement_loop.before_loop
    async def before_close_announcement_loop(self) -> None:
        await self._bot.wait_until_ready()
