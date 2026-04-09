from __future__ import annotations

import discord

from src.constants import (
    get_max_songs_for_day,
    LONG_SONG_MESSAGE,
    MAX_SONG_DURATION_SECONDS,
    UNAUTHORIZED_BUTTON_MESSAGE,
)
from src.models import YouTubeResult
from src.services.playlist_service import PlaylistService
from src.utils.response_embed import build_song_list_embed, build_status_embed
from src.utils.song_format import format_song_display


class SongSelectButton(discord.ui.Button["SongSelectView"]):
    def __init__(self, index: int) -> None:
        super().__init__(label=str(index + 1), style=discord.ButtonStyle.primary)
        self.index = index

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.view is None:
            return
        await self.view.handle_selection(interaction, self.index)


class CancelSelectButton(discord.ui.Button["SongSelectView"]):
    def __init__(self) -> None:
        super().__init__(label="취소", style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.view is None:
            return
        await self.view.handle_cancel(interaction)


class SongSelectView(discord.ui.View):
    def __init__(
        self,
        requester_id: int,
        day: str,
        results: list[YouTubeResult],
        playlist_service: PlaylistService,
        timeout: float = 120.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.requester_id = requester_id
        self.day = day
        self.results = results
        self.playlist_service = playlist_service
        self._completed = False

        for index, _ in enumerate(results):
            self.add_item(SongSelectButton(index))
        self.add_item(CancelSelectButton())

    async def handle_selection(self, interaction: discord.Interaction, index: int) -> None:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(UNAUTHORIZED_BUTTON_MESSAGE, ephemeral=True)
            return

        if self._completed:
            await interaction.response.send_message("이미 선택이 완료되었습니다.", ephemeral=True)
            return

        selected = self.results[index]
        selected_display = selected.display_title
        if (
            selected.duration_seconds is not None
            and selected.duration_seconds > MAX_SONG_DURATION_SECONDS
        ):
            await interaction.response.send_message(LONG_SONG_MESSAGE, ephemeral=True)
            return

        self._completed = True

        result = await self.playlist_service.register_song(
            user_id=self.requester_id,
            day=self.day,
            title=selected_display,
            url=selected.url,
        )

        for child in self.children:
            child.disabled = True

        if result.success:
            titles = [format_song_display(title) for title in result.playlist_titles]
            public_embed = build_song_list_embed(
                title=f"{self.day}요일 현재 플리",
                songs=titles,
                kind="success",
                description=(
                    f"{interaction.user.mention} 님이 곡을 신청했습니다.\n"
                    f"선택한 곡: **{selected_display}**"
                ),
                max_songs=get_max_songs_for_day(self.day),
            )
            if interaction.channel is not None:
                await interaction.channel.send(embed=public_embed)
                content = "곡 등록이 완료되었습니다. 채널에 공개 결과를 전송했습니다."
            else:
                content = "곡 등록이 완료되었습니다."
        else:
            content = "신청이 거절되었습니다."
            embed = build_status_embed(result.message, title="신청 실패")
            await interaction.response.edit_message(content=content, embed=embed, view=self)
            return

        await interaction.response.edit_message(content=content, embed=None, view=self)

    async def handle_cancel(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(UNAUTHORIZED_BUTTON_MESSAGE, ephemeral=True)
            return

        if self._completed:
            await interaction.response.send_message("이미 선택이 완료되었습니다.", ephemeral=True)
            return

        self._completed = True
        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(
            content="신청이 취소되었습니다.",
            embed=None,
            view=self,
        )

    async def on_timeout(self) -> None:
        if self._completed:
            return
        for child in self.children:
            child.disabled = True
