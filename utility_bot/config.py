"""Load bot settings from environment variables (and a local .env file).

All settings live in one frozen dataclass so the rest of the code never has to
touch os.environ directly. The token is excluded from repr() so it can't leak
into logs or tracebacks by accident.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_PRICE_DB = "/home/ubuntu/price-tracker/data/price_history.db"


class ConfigError(Exception):
    """Raised when a required setting is missing or malformed."""


@dataclass(frozen=True)
class Settings:
    token: str = field(repr=False)  # never shown in repr / logs
    bot_db_path: Path = Path("data/utility_bot.db")
    price_db_path: Path = Path(DEFAULT_PRICE_DB)
    log_level: str = "INFO"
    log_dir: Path = Path("logs")
    dev_guild_id: int | None = None
    currency_symbol: str = "£"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        """Build settings from a mapping (defaults to os.environ)."""
        env = os.environ if env is None else env

        token = env.get("DISCORD_TOKEN", "").strip()
        if not token:
            raise ConfigError(
                "DISCORD_TOKEN is not set. Put it in a .env file next to the bot "
                "(see .env.example)."
            )

        guild_raw = env.get("DEV_GUILD_ID", "").strip()
        if guild_raw and not guild_raw.isdigit():
            raise ConfigError("DEV_GUILD_ID must be a numeric server ID.")

        log_level = env.get("LOG_LEVEL", "INFO").strip().upper()
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ConfigError(f"LOG_LEVEL {log_level!r} is not a valid logging level.")

        return cls(
            token=token,
            bot_db_path=Path(env.get("BOT_DB_PATH", "data/utility_bot.db")),
            price_db_path=Path(env.get("PRICE_DB_PATH", DEFAULT_PRICE_DB)),
            log_level=log_level,
            log_dir=Path(env.get("LOG_DIR", "logs")),
            dev_guild_id=int(guild_raw) if guild_raw else None,
            currency_symbol=env.get("CURRENCY_SYMBOL", "£"),
        )


def load_settings(env_file: str | Path = ".env") -> Settings:
    """Read .env (if present) into the environment, then build Settings."""
    load_dotenv(env_file, override=False)
    return Settings.from_env()
