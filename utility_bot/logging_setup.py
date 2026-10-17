"""Logging to stdout (picked up by journald under systemd) and a rotating file.

A RedactingFilter scrubs secrets (the bot token) from every record, as a
safety net in case a library ever logs something it shouldn't.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
REDACTED = "[REDACTED]"


class RedactingFilter(logging.Filter):
    """Replace any secret value that appears in a log message."""

    def __init__(self, secrets: Iterable[str]) -> None:
        super().__init__()
        # Ignore empty/very short strings so we don't redact random text.
        self._secrets = [s for s in secrets if s and len(s) >= 8]

    def filter(self, record: logging.LogRecord) -> bool:
        if not self._secrets:
            return True
        message = record.getMessage()
        if any(secret in message for secret in self._secrets):
            for secret in self._secrets:
                message = message.replace(secret, REDACTED)
            # Freeze the cleaned text so handlers don't re-format the raw args.
            record.msg, record.args = message, None
        return True


def setup_logging(level: str, log_dir: Path, secrets: Iterable[str] = ()) -> None:
    """Configure the root logger once at startup."""
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(LOG_FORMAT)
    redactor = RedactingFilter(secrets)

    stream = logging.StreamHandler()
    file = RotatingFileHandler(
        log_dir / "utility-bot.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    for handler in (stream, file):
        handler.setFormatter(formatter)
        handler.addFilter(redactor)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    root.addHandler(stream)
    root.addHandler(file)

    # discord.py's HTTP layer is chatty at INFO; keep it to warnings.
    logging.getLogger("discord.http").setLevel(logging.WARNING)
