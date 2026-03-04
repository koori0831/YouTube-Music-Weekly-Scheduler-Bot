from __future__ import annotations

import random

import discord
from discord import app_commands
from discord.ext import commands

from src.constants import DAY_CHOICES, MAX_SONGS_PER_DAY, NO_RESULTS_MESSAGE
from src.db.repositories import (
    DaySettingsRepository,
    MetaRepository,
    PlaylistRepository,
    UserStatsRepository,
)
from src.services.playlist_service import PlaylistService
from src.services.youtube_service import YouTubeService
from src.utils.response_embed import build_song_list_embed, build_status_embed
from src.utils.song_format import format_song_display
from src.views.song_select_view import SongSelectView


class MusicCog(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
        playlist_service: PlaylistService,
        playlist_repo: PlaylistRepository,
        day_settings_repo: DaySettingsRepository,
        user_stats_repo: UserStatsRepository,
        meta_repo: MetaRepository,
        youtube_service: YouTubeService,
    ) -> None:
        self.bot = bot
        self.playlist_service = playlist_service
        self.playlist_repo = playlist_repo
        self.day_settings_repo = day_settings_repo
        self.user_stats_repo = user_stats_repo
        self.meta_repo = meta_repo
        self.youtube_service = youtube_service

    def _restricted_guild_id(self) -> int | None:
        settings = getattr(self.bot, "settings", None)
        return getattr(settings, "discord_guild_id", None)

    async def _is_user_in_restricted_guild(self, user_id: int) -> bool:
        guild_id = self._restricted_guild_id()
        if guild_id is None:
            return True

        guild = self.bot.get_guild(guild_id)
        if guild is None:
            try:
                guild = await self.bot.fetch_guild(guild_id)
            except discord.HTTPException:
                return False

        if guild.get_member(user_id) is not None:
            return True

        try:
            await guild.fetch_member(user_id)
            return True
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return False

    async def cog_app_command_check(self, interaction: discord.Interaction) -> bool:
        guild_id = self._restricted_guild_id()
        if guild_id is None:
            return True

        if await self._is_user_in_restricted_guild(interaction.user.id):
            return True

        raise app_commands.CheckFailure(
            f"이 봇은 지정된 서버 멤버만 사용할 수 있습니다. (DISCORD_GUILD_ID={guild_id})"
        )

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.CheckFailure):
            message = str(error) or "명령어를 사용할 권한이 없습니다."
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
            return
        raise error

    def _is_admin(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            return False
        member = interaction.user
        if not isinstance(member, discord.Member):
            return False
        perms = member.guild_permissions
        return perms.administrator or perms.manage_guild

    def _build_help_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="📘 YouTube Music Weekly Scheduler Bot 도움말",
            description="기본 룰과 명령어 사용법입니다.",
            color=discord.Color.gold(),
        )
        embed.add_field(
            name="기본 룰",
            value=(
                "- 운영 요일: 월~금\n"
                "- 요일당 최대 12곡\n"
                "- 일반 유저 주간 최대 2곡\n"
                "- 매주 일요일 09:00(KST) 자동 초기화"
            ),
            inline=False,
        )
        embed.add_field(
            name="시간 규칙",
            value=(
                "- 기준: 서버 시간\n"
                "- 당일 00:40 이전에는 전날 요일 기준으로 신청 가능\n"
                "- 금요일 00:40 이후 신청은 일요일 09:00 이후 다시 가능"
            ),
            inline=False,
        )
        embed.add_field(
            name="일반 명령어",
            value=(
                "- `/신청 제목:<곡명> 요일:<월~금>`: 곡 검색 후 선택 신청\n"
                "- `/보기 요일:<월~금>`: 해당 요일 플레이리스트 조회\n"
                "- `/help`: 도움말 보기"
            ),
            inline=False,
        )
        embed.add_field(
            name="관리자 명령어",
            value=(
                "- `/플리제한 요일 상태 [유저]`: 요일 잠금/해제, 독점 유저 지정\n"
                "- `/셔플 요일`: 요일 곡 목록 셔플\n"
                "- `/삭제 요일 번호`: 해당 요일에서 번호로 곡 삭제(신청 횟수 1회 복구)\n"
                "- `/db초기화 확인:초기화`: DB 초기화"
            ),
            inline=False,
        )
        return embed

    @app_commands.command(name="help", description="봇 사용법과 운영 규칙을 안내합니다.")
    async def help_command(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(embed=self._build_help_embed(), ephemeral=True)

    @app_commands.command(name="도움말", description="봇 사용법과 운영 규칙을 안내합니다.")
    async def help_command_ko(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(embed=self._build_help_embed(), ephemeral=True)

    @app_commands.command(name="신청", description="요일 플레이리스트에 노래를 신청합니다.")
    @app_commands.describe(제목="유튜브에서 검색할 곡 제목", 요일="신청할 요일")
    @app_commands.choices(
        요일=[app_commands.Choice(name=day, value=day) for day in DAY_CHOICES]
    )
    async def request_song(
        self,
        interaction: discord.Interaction,
        제목: str,
        요일: app_commands.Choice[str],
    ) -> None:
        day = 요일.value
        validation = await self.playlist_service.validate_request(interaction.user.id, day)
        if not validation.allowed:
            message = validation.message or "신청할 수 없습니다."
            embed = build_status_embed(message, title="신청 불가")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            results = await self.youtube_service.search_music(제목, limit=3)
        except Exception as exc:
            await interaction.followup.send(f"YouTube 검색 중 오류가 발생했습니다: {exc}", ephemeral=True)
            return

        if not results:
            await interaction.followup.send(NO_RESULTS_MESSAGE, ephemeral=True)
            return

        embeds: list[discord.Embed] = []
        for idx, item in enumerate(results, start=1):
            embed = discord.Embed(
                title=f"{idx}. {item.display_title}",
                url=item.url,
                description=f"{day}요일 신청 후보",
                color=discord.Color.blue(),
            )
            if item.thumbnail_url:
                embed.set_image(url=item.thumbnail_url)
            embeds.append(embed)

        view = SongSelectView(
            requester_id=interaction.user.id,
            day=day,
            results=results,
            playlist_service=self.playlist_service,
        )
        await interaction.followup.send(embeds=embeds, view=view, ephemeral=True)

    @app_commands.command(name="플리제한", description="요일별 플리 잠금/해제를 설정합니다.")
    @app_commands.default_permissions(administrator=True, manage_guild=True)
    @app_commands.describe(요일="설정할 요일", 상태="잠금 또는 해제", 유저="독점 권한을 줄 유저")
    @app_commands.choices(
        요일=[app_commands.Choice(name=day, value=day) for day in DAY_CHOICES],
        상태=[
            app_commands.Choice(name="잠금", value="잠금"),
            app_commands.Choice(name="해제", value="해제"),
        ],
    )
    async def set_playlist_lock(
        self,
        interaction: discord.Interaction,
        요일: app_commands.Choice[str],
        상태: app_commands.Choice[str],
        유저: discord.Member | None = None,
    ) -> None:
        if not self._is_admin(interaction):
            await interaction.response.send_message("관리자 권한이 필요합니다.", ephemeral=True)
            return

        day = 요일.value
        state = 상태.value

        if state == "해제":
            await self.day_settings_repo.set_lock(day, False, None)
            await interaction.response.send_message(f"{day}요일 플레이리스트 제한을 해제했습니다.")
            return

        exclusive_user_id = 유저.id if 유저 else None
        await self.day_settings_repo.set_lock(day, True, exclusive_user_id)
        deleted_count = await self.playlist_repo.clear_by_day(day)
        await self.user_stats_repo.rebuild_from_playlists()

        if 유저:
            await interaction.response.send_message(
                f"{day}요일을 잠금 처리하고 {유저.mention}에게 독점 권한을 부여했습니다. "
                f"(기존 신청곡 {deleted_count}개 삭제)"
            )
        else:
            await interaction.response.send_message(
                f"{day}요일을 잠금 처리했습니다. (전체 차단, 기존 신청곡 {deleted_count}개 삭제)"
            )

    @app_commands.command(name="보기", description="해당 요일 플레이리스트 현황을 확인합니다.")
    @app_commands.describe(요일="조회할 요일")
    @app_commands.choices(
        요일=[app_commands.Choice(name=day, value=day) for day in DAY_CHOICES]
    )
    async def view_day(
        self,
        interaction: discord.Interaction,
        요일: app_commands.Choice[str],
    ) -> None:
        day = 요일.value
        songs = await self.playlist_repo.list_by_day(day)
        titles = [format_song_display(str(song["title"])) for song in songs]
        embed = build_song_list_embed(
            title=f"{day}요일 현재 현황",
            songs=titles,
            kind="view",
            max_songs=MAX_SONGS_PER_DAY,
            empty_text=f"{day}요일 플레이리스트가 비어 있습니다.",
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="셔플", description="해당 요일의 곡 제목 목록을 셔플하여 보여줍니다.")
    @app_commands.default_permissions(administrator=True, manage_guild=True)
    @app_commands.describe(요일="셔플할 요일")
    @app_commands.choices(
        요일=[app_commands.Choice(name=day, value=day) for day in DAY_CHOICES]
    )
    async def shuffle_day(
        self,
        interaction: discord.Interaction,
        요일: app_commands.Choice[str],
    ) -> None:
        if not self._is_admin(interaction):
            await interaction.response.send_message("관리자 권한이 필요합니다.", ephemeral=True)
            return

        day = 요일.value
        songs = await self.playlist_repo.list_by_day(day)
        titles = [format_song_display(str(song["title"])) for song in songs]
        random.shuffle(titles)
        embed = build_song_list_embed(
            title=f"{day}요일 셔플 결과",
            songs=titles,
            kind="shuffle",
            empty_text=f"{day}요일 플레이리스트가 비어 있습니다.",
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="삭제", description="해당 요일 플레이리스트에서 번호로 곡을 삭제합니다.")
    @app_commands.default_permissions(administrator=True, manage_guild=True)
    @app_commands.describe(요일="삭제할 곡의 요일", 번호="해당 요일 플레이리스트 번호(1부터 시작)")
    @app_commands.choices(
        요일=[app_commands.Choice(name=day, value=day) for day in DAY_CHOICES]
    )
    async def delete_song(
        self,
        interaction: discord.Interaction,
        요일: app_commands.Choice[str],
        번호: int,
    ) -> None:
        if not self._is_admin(interaction):
            await interaction.response.send_message("관리자 권한이 필요합니다.", ephemeral=True)
            return

        day = 요일.value
        songs = await self.playlist_repo.list_by_day(day)
        if not songs:
            await interaction.response.send_message(
                f"{day}요일 플레이리스트가 비어 있어 삭제할 곡이 없습니다.",
                ephemeral=True,
            )
            return

        if 번호 < 1 or 번호 > len(songs):
            await interaction.response.send_message(
                f"유효하지 않은 번호입니다. 현재 {day}요일은 1번부터 {len(songs)}번까지 있습니다.",
                ephemeral=True,
            )
            return

        target = songs[번호 - 1]
        song_id = int(target["id"])
        deleted = await self.playlist_repo.delete_by_id(song_id)
        if not deleted:
            await interaction.response.send_message(
                "삭제에 실패했습니다. 잠시 후 다시 시도해주세요.",
                ephemeral=True,
            )
            return

        title = format_song_display(str(target["title"]))
        requester_id = int(target["user_id"])
        await self.user_stats_repo.decrement(requester_id)
        requester_mention = f"<@{requester_id}>"
        deleter_mention = interaction.user.mention

        await interaction.response.send_message(
            (
                f"🗑️ {day}요일 플레이리스트 {번호}번 곡이 삭제되었습니다.\n"
                f"곡: **{title}**\n"
                f"삭제자: {deleter_mention}\n"
                f"신청자: {requester_mention}\n"
                "삭제 사유는 삭제자에게 문의해주세요."
            )
        )

    @app_commands.command(name="db초기화", description="DB 데이터를 초기 상태로 초기화합니다.")
    @app_commands.default_permissions(administrator=True, manage_guild=True)
    @app_commands.describe(확인='실행하려면 "초기화"를 입력하세요')
    async def reset_db(
        self,
        interaction: discord.Interaction,
        확인: str,
    ) -> None:
        if not self._is_admin(interaction):
            await interaction.response.send_message("관리자 권한이 필요합니다.", ephemeral=True)
            return

        if 확인.strip() != "초기화":
            await interaction.response.send_message(
                'DB 초기화를 취소했습니다. 실행하려면 확인 값에 "초기화"를 입력하세요.',
                ephemeral=True,
            )
            return

        await self.playlist_repo.clear_all()
        await self.user_stats_repo.reset_all()
        await self.day_settings_repo.reset_all()
        await self.meta_repo.clear_all()
        await interaction.response.send_message(
            "DB 초기화가 완료되었습니다. (플리/유저통계/요일잠금/메타 초기화)",
            ephemeral=True,
        )


async def setup(
    bot: commands.Bot,
    playlist_service: PlaylistService,
    playlist_repo: PlaylistRepository,
    day_settings_repo: DaySettingsRepository,
    user_stats_repo: UserStatsRepository,
    meta_repo: MetaRepository,
    youtube_service: YouTubeService,
) -> None:
    await bot.add_cog(
        MusicCog(
            bot=bot,
            playlist_service=playlist_service,
            playlist_repo=playlist_repo,
            day_settings_repo=day_settings_repo,
            user_stats_repo=user_stats_repo,
            meta_repo=meta_repo,
            youtube_service=youtube_service,
        )
    )
