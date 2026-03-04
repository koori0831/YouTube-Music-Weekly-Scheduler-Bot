from __future__ import annotations

from dataclasses import dataclass

from src.utils.song_format import format_song_display


@dataclass(frozen=True)
class DaySetting:
    day_of_week: str
    is_locked: bool
    exclusive_user_id: int | None


@dataclass(frozen=True)
class YouTubeResult:
    title: str
    url: str
    artist: str | None = None
    thumbnail_url: str | None = None
    duration_seconds: int | None = None

    @property
    def display_title(self) -> str:
        return format_song_display(self.title, self.artist)


@dataclass(frozen=True)
class ValidationResult:
    allowed: bool
    message: str | None = None
    bypass_weekly_limit: bool = False


@dataclass(frozen=True)
class RegisterResult:
    success: bool
    message: str
    playlist_titles: list[str]
