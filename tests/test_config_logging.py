import logging
from pathlib import Path

import pytest

from utility_bot.config import ConfigError, Settings
from utility_bot.logging_setup import REDACTED, RedactingFilter

FAKE_TOKEN = "MTIzNDU2Nzg5.fake.token-value-for-tests"


def test_settings_from_env_defaults() -> None:
    settings = Settings.from_env({"DISCORD_TOKEN": FAKE_TOKEN})
    assert settings.token == FAKE_TOKEN
    assert settings.dev_guild_id is None
    assert settings.bot_db_path == Path("data/utility_bot.db")
    assert settings.log_level == "INFO"


def test_settings_overrides() -> None:
    settings = Settings.from_env(
        {"DISCORD_TOKEN": FAKE_TOKEN, "DEV_GUILD_ID": "123", "LOG_LEVEL": "debug", "PRICE_DB_PATH": "/x.db"}
    )
    assert settings.dev_guild_id == 123
    assert settings.log_level == "DEBUG"
    assert settings.price_db_path == Path("/x.db")


@pytest.mark.parametrize(
    "env",
    [{}, {"DISCORD_TOKEN": "  "}, {"DISCORD_TOKEN": FAKE_TOKEN, "DEV_GUILD_ID": "abc"},
     {"DISCORD_TOKEN": FAKE_TOKEN, "LOG_LEVEL": "LOUD"}],
)
def test_settings_errors(env) -> None:
    with pytest.raises(ConfigError):
        Settings.from_env(env)


def test_token_not_in_repr() -> None:
    assert FAKE_TOKEN not in repr(Settings.from_env({"DISCORD_TOKEN": FAKE_TOKEN}))


def test_redacting_filter_scrubs_token() -> None:
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "token is %s!", (FAKE_TOKEN,), None)
    RedactingFilter([FAKE_TOKEN]).filter(record)
    assert record.getMessage() == f"token is {REDACTED}!"


def test_redacting_filter_leaves_other_messages() -> None:
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "hello %s", ("world",), None)
    RedactingFilter([FAKE_TOKEN]).filter(record)
    assert record.getMessage() == "hello world"
