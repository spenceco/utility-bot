"""Smoke tests for the Discord layer that don't need a network connection."""

from types import SimpleNamespace

import discord
from discord import app_commands

from utility_bot.bot import EXTENSIONS, UtilityBot
from utility_bot.cogs.help import EXAMPLES, iter_commands
from utility_bot.cogs.polls import build_poll_embed, build_poll_view
from utility_bot.cogs.price import build_price_embed
from utility_bot.config import Settings
from utility_bot.core.polls import PollStore
from utility_bot.core.prices import PriceRepository
from utility_bot.errors import UserFacingError, describe_error


def _bot(tmp_path, price_db=None) -> UtilityBot:
    settings = Settings(
        token="x" * 30, bot_db_path=tmp_path / "bot.db", price_db_path=price_db or tmp_path / "none.db"
    )
    return UtilityBot(settings)


async def test_all_cogs_load_and_help_covers_them(tmp_path) -> None:
    bot = _bot(tmp_path)
    for extension in EXTENSIONS:
        await bot.load_extension(extension)
    names = {c.qualified_name for c in iter_commands(bot.tree)}
    assert names == {"remind", "reminders list", "reminders cancel", "poll", "price", "stats", "help"}
    assert names == set(EXAMPLES)  # every command has a help example
    for extension in EXTENSIONS:
        await bot.unload_extension(extension)  # also stops the reminder loop
    bot.db.close()


def test_poll_embed_and_buttons(tmp_path, bot_db) -> None:
    store = PollStore(bot_db)
    poll = store.create(guild_id=1, channel_id=2, author_id=3, question="Lunch?", options=["A", "B"], created_at=0)
    store.vote(poll.id, 10, 1)
    poll = store.get(poll.id)

    view = build_poll_view(poll)
    labels = [item.item.label for item in view.children if hasattr(item, "item")]
    assert labels == ["A · 0", "B · 1", "End poll"]
    assert "1 vote" in build_poll_embed(poll).footer.text

    poll.closed = True
    closed_view = build_poll_view(poll)
    assert all(child.item.disabled for child in closed_view.children)
    assert "B" in build_poll_embed(poll).fields[0].value  # winner announced


def test_price_embed(price_db) -> None:
    book = PriceRepository(price_db).find("sapiens").book
    embed = build_price_embed(book, "£", ["Other Book"])
    assert "£49.99" in embed.description
    assert "-7.8%" in embed.description
    assert embed.colour == discord.Colour.green()  # price dropped
    assert any(f.name == "Other matches" for f in embed.fields)


def _interaction(name: str = "remind"):
    return SimpleNamespace(command=SimpleNamespace(qualified_name=name))


def test_error_messages_are_friendly() -> None:
    inter = _interaction()
    assert describe_error(inter, UserFacingError("Nope")) == "Nope"
    cooldown = app_commands.CommandOnCooldown(app_commands.Cooldown(1, 5), 3.2)
    assert describe_error(inter, cooldown) == "⏳ Slow down! You can use `/remind` again in 4 seconds."
    assert "server" in describe_error(inter, app_commands.NoPrivateMessage())
    assert describe_error(inter, app_commands.AppCommandError("boom")) is None  # unexpected -> logged
