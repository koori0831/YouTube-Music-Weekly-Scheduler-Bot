from __future__ import annotations

import discord


def _song_embed_style(kind: str) -> tuple[str, discord.Color]:
    if kind == "success":
        return ("✅", discord.Color.green())
    if kind == "view":
        return ("📋", discord.Color.blurple())
    if kind == "shuffle":
        return ("🔀", discord.Color.teal())
    return ("🎵", discord.Color.blue())


def build_status_embed(message: str, title: str = "안내") -> discord.Embed:
    reason: str | None = None
    current_line: str | None = None
    available_line: str | None = None
    locked_line: str | None = None
    full_line: str | None = None
    notices: list[str] = []

    for raw in message.splitlines():
        line = raw.strip()
        if not line:
            continue
        if "서버 현재 요일:" in line:
            current_line = line.split("서버 현재 요일:", 1)[1].strip()
            continue
        if "신청 가능 요일:" in line:
            available_line = line.split("신청 가능 요일:", 1)[1].strip()
            continue
        if "잠금(상점 사용):" in line:
            locked_line = line.split("잠금(상점 사용):", 1)[1].strip()
            continue
        if "플리 꽉참:" in line:
            full_line = line.split("플리 꽉참:", 1)[1].strip()
            continue
        if line.startswith("⚠") or line.startswith("🕘"):
            notices.append(line)
            continue
        if reason is None:
            reason = line
            continue
        notices.append(line)

    embed = discord.Embed(
        title=title,
        description=reason or "요청을 처리할 수 없습니다.",
        color=discord.Color.orange(),
    )
    if current_line:
        embed.add_field(name="현재 기준", value=current_line, inline=False)
    if available_line:
        embed.add_field(name="신청 가능", value=available_line, inline=False)
    if locked_line:
        embed.add_field(name="잠금(상점 사용)", value=locked_line, inline=False)
    if full_line:
        embed.add_field(name="플리 꽉참", value=full_line, inline=False)
    if notices:
        embed.add_field(name="추가 안내", value="\n".join(notices), inline=False)
    return embed


def build_song_list_embed(
    title: str,
    songs: list[str],
    *,
    kind: str = "default",
    description: str | None = None,
    max_songs: int | None = None,
    empty_text: str = "곡이 없습니다.",
    color: discord.Color | None = None,
) -> discord.Embed:
    icon, default_color = _song_embed_style(kind)
    full_title = title
    if max_songs is not None:
        full_title = f"{title} ({len(songs)}곡/{max_songs}곡)"

    embed = discord.Embed(
        title=f"{icon} {full_title}",
        description=description,
        color=color or default_color,
    )

    if songs:
        lines = [f"{idx}. {song}" for idx, song in enumerate(songs, start=1)]
        embed.add_field(name="곡 목록", value="\n".join(lines), inline=False)
    else:
        embed.add_field(name="곡 목록", value=empty_text, inline=False)

    return embed
