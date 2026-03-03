from __future__ import annotations

from html import unescape


def format_song_display(title: str, artist: str | None = None) -> str:
    clean_title = unescape((title or "").strip())
    clean_artist = unescape((artist or "").strip())

    if not clean_title:
        clean_title = "제목 없음"

    # 이미 "가수 - 곡 제목" 형태라면 그대로 사용
    if " - " in clean_title:
        return clean_title

    if clean_artist:
        return f"{clean_artist} - {clean_title}"

    return f"알 수 없음 - {clean_title}"
