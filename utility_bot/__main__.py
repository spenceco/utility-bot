"""Entry point: `python -m utility_bot`."""

from __future__ import annotations

import logging
import sys

import discord

from .bot import UtilityBot
from .config import ConfigError, load_settings
from .logging_setup import setup_logging

# Exit code 2 = configuration problem. The systemd unit is told not to
# restart on it, since restarting won't fix a missing or wrong token.
EXIT_CONFIG_ERROR = 2


def main() -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    setup_logging(settings.log_level, settings.log_dir, secrets=[settings.token])
    log = logging.getLogger("utility_bot")
    log.info("Starting utility-bot (settings: %r)", settings)  # token is hidden by repr=False

    bot = UtilityBot(settings)
    try:
        # log_handler=None: keep our logging setup instead of discord.py's default.
        bot.run(settings.token, log_handler=None)
    except discord.LoginFailure:
        log.critical("Discord rejected the token. Check DISCORD_TOKEN in .env.")
        return EXIT_CONFIG_ERROR
    return 0


if __name__ == "__main__":
    sys.exit(main())
