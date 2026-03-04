from __future__ import annotations

import discord

from src.utils.response_embed import build_song_list_embed, build_status_embed


def test_build_status_embed_parses_status_lines() -> None:
    message = (
        "이미 지난 요일입니다.\n\n"
        "📅 서버 현재 요일: 목요일\n"
        "✅ 신청 가능 요일: 목요일, 금요일\n"
        "🔒 잠금(상점 사용): 없음\n"
        "📦 플리 꽉참: 없음\n"
        "⚠️ 현재 신청 가능한 요일이 없습니다.\n"
        "🕘 금요일 00:40 이후에는 곡 신청이 잠깁니다."
    )

    embed = build_status_embed(message, title="신청 불가")

    assert embed.title == "신청 불가"
    assert embed.description == "이미 지난 요일입니다."
    assert len(embed.fields) == 5
    assert embed.fields[0].name == "현재 기준"
    assert embed.fields[1].name == "신청 가능"
    assert embed.fields[2].name == "잠금(상점 사용)"
    assert embed.fields[3].name == "플리 꽉참"
    assert embed.fields[4].name == "추가 안내"


def test_build_status_embed_with_plain_message() -> None:
    embed = build_status_embed("신청할 수 없습니다.", title="안내")
    assert embed.title == "안내"
    assert embed.description == "신청할 수 없습니다."
    assert len(embed.fields) == 0


def test_build_song_list_embed_with_songs() -> None:
    embed = build_song_list_embed(
        title="수요일 현재 현황",
        songs=["A", "B"],
        kind="view",
        max_songs=12,
    )
    assert embed.title == "📋 수요일 현재 현황 (2곡/12곡)"
    assert embed.color == discord.Color.blurple()
    assert len(embed.fields) == 1
    assert embed.fields[0].name == "곡 목록"
    assert "1. A" in embed.fields[0].value
    assert "2. B" in embed.fields[0].value


def test_build_song_list_embed_with_empty_list() -> None:
    embed = build_song_list_embed(
        title="목요일 셔플 결과",
        songs=[],
        kind="shuffle",
        empty_text="목요일 플레이리스트가 비어 있습니다.",
    )
    assert embed.title == "🔀 목요일 셔플 결과"
    assert embed.color == discord.Color.teal()
    assert len(embed.fields) == 1
    assert embed.fields[0].value == "목요일 플레이리스트가 비어 있습니다."
