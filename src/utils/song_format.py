from __future__ import annotations

from html import unescape


def _normalize_name_for_compare(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def format_song_display(title: str, artist: str | None = None) -> str:
    clean_title = unescape((title or "").strip())
    clean_artist = unescape((artist or "").strip())

    if not clean_title:
        clean_title = "제목 없음"

    if " - " in clean_title:
        # If title already starts with artist, avoid duplicate "artist - artist - title".
        if clean_artist:
            maybe_artist = clean_title.split(" - ", 1)[0]
            if _normalize_name_for_compare(maybe_artist) == _normalize_name_for_compare(clean_artist):
                return clean_title
            return f"{clean_artist} - {clean_title}"
        return clean_title

    if clean_artist:
        return f"{clean_artist} - {clean_title}"

    return f"알 수 없음 - {clean_title}"
