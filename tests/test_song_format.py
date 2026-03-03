from __future__ import annotations

from src.utils.song_format import format_song_display


def test_format_song_display_with_artist():
    assert format_song_display("Hype Boy", "NewJeans") == "NewJeans - Hype Boy"


def test_format_song_display_keeps_existing_pair_format():
    assert format_song_display("IVE - REBEL HEART", "IVE") == "IVE - REBEL HEART"


def test_format_song_display_hyphenated_title_with_distinct_artist():
    assert (
        format_song_display("Yumeutsutsu - Daydream", "Ado")
        == "Ado - Yumeutsutsu - Daydream"
    )


def test_format_song_display_without_artist_fallback():
    assert format_song_display("Dynamite") == "알 수 없음 - Dynamite"


def test_format_song_display_unescapes_html_entities():
    raw = "IT&#39;S GOING DOWN NOW &quot;Live&quot;"
    assert format_song_display(raw, "Lotus Juice") == "Lotus Juice - IT'S GOING DOWN NOW \"Live\""
