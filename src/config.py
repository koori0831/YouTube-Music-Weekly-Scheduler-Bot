from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    discord_bot_token: str
    youtube_api_key: str | None = None
    db_path: str = "bot.db"
    discord_guild_id: int | None = None
    song_request_channel_id: int | None = None
    song_announcement_channel_id: int | None = None


class ConfigError(ValueError):
    pass


def load_settings() -> Settings:
    token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    youtube_key = os.getenv("YOUTUBE_API_KEY", "").strip() or None
    db_path = os.getenv("DB_PATH", "bot.db").strip() or "bot.db"

    guild_id_raw = os.getenv("DISCORD_GUILD_ID", "").strip()
    guild_id = int(guild_id_raw) if guild_id_raw else None
    request_channel_id = _parse_optional_int("SONG_REQUEST_CHANNEL_ID")
    announcement_channel_id = _parse_optional_int("SONG_ANNOUNCEMENT_CHANNEL_ID")

    if not token:
        raise ConfigError("DISCORD_BOT_TOKEN 환경변수가 필요합니다.")

    return Settings(
        discord_bot_token=token,
        youtube_api_key=youtube_key,
        db_path=db_path,
        discord_guild_id=guild_id,
        song_request_channel_id=request_channel_id,
        song_announcement_channel_id=announcement_channel_id,
    )


def _parse_optional_int(env_name: str) -> int | None:
    raw = os.getenv(env_name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{env_name} 환경변수는 숫자 채널 ID여야 합니다.") from exc
