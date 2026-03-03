from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    discord_bot_token: str
    youtube_api_key: str
    db_path: str = "bot.db"
    discord_guild_id: int | None = None


class ConfigError(ValueError):
    pass


def load_settings() -> Settings:
    token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    youtube_key = os.getenv("YOUTUBE_API_KEY", "").strip()
    db_path = os.getenv("DB_PATH", "bot.db").strip() or "bot.db"

    guild_id_raw = os.getenv("DISCORD_GUILD_ID", "").strip()
    guild_id = int(guild_id_raw) if guild_id_raw else None

    if not token:
        raise ConfigError("DISCORD_BOT_TOKEN 환경변수가 필요합니다.")
    if not youtube_key:
        raise ConfigError("YOUTUBE_API_KEY 환경변수가 필요합니다.")

    return Settings(
        discord_bot_token=token,
        youtube_api_key=youtube_key,
        db_path=db_path,
        discord_guild_id=guild_id,
    )
