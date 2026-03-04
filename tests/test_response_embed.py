from __future__ import annotations

from src.utils.response_embed import build_status_embed


def test_build_status_embed_parses_status_lines() -> None:
    message = (
        "이미 지난 요일입니다.\n\n"
        "📅 서버 현재 요일: 목요일\n"
        "✅ 신청 가능 요일: 목요일, 금요일\n"
        "🔒 잠금(상점 사용): 없음\n"
        "📦 플리 꽉참: 없음\n"
        "⚠️ 현재 신청 가능한 요일이 없습니다.\n"
        "🕘 금요일 03:00 이후에는 곡 신청이 잠깁니다."
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
