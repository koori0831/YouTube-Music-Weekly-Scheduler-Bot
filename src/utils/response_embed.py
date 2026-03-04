from __future__ import annotations

import discord


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
        if line.startswith("📅 "):
            current_line = line.removeprefix("📅 ").strip()
            continue
        if line.startswith("✅ "):
            available_line = line.removeprefix("✅ ").strip()
            continue
        if line.startswith("🔒 "):
            locked_line = line.removeprefix("🔒 ").strip()
            continue
        if line.startswith("📦 "):
            full_line = line.removeprefix("📦 ").strip()
            continue
        if line.startswith("⚠️ ") or line.startswith("🕘 "):
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
