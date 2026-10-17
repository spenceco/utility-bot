"""/price: look up a book in the price-tracker database.

Title autocomplete is powered by the same database, and lookups forgive
typos ("harry poter" still finds the right book).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from ..core.formatting import sparkline, star_rating, truncate
from ..core.prices import BookPrice, PriceDatabaseError
from ..errors import UserFacingError

if TYPE_CHECKING:
    from ..bot import UtilityBot

log = logging.getLogger(__name__)

HISTORY_ROWS = 8        # price changes listed in the embed
SPARKLINE_POINTS = 30   # daily checks drawn in the mini chart


def _ts(dt) -> int:
    return int(dt.timestamp())


def format_change(book: BookPrice, currency: str) -> str:
    if book.change == 0:
        return "No change since tracking began"
    arrow = "🔻" if book.change < 0 else "🔺"
    return f"{arrow} {currency}{abs(book.change):.2f} ({book.change_pct:+.1f}%)"


def build_price_embed(book: BookPrice, currency: str, other_matches: list[str]) -> discord.Embed:
    # Green if the latest move was a drop, red if a rise, blurple otherwise.
    previous = book.previous_price
    if previous is not None and book.price < previous:
        colour = discord.Colour.green()
    elif previous is not None and book.price > previous:
        colour = discord.Colour.red()
    else:
        colour = discord.Colour.blurple()

    if not book.active:
        availability = "⚠️ No longer listed"
    else:
        availability = "✅ In stock" if book.in_stock else "❌ Out of stock"

    embed = discord.Embed(
        title=truncate(book.title, 256),
        url=book.url,
        description=f"## {currency}{book.price:.2f}\n{format_change(book, currency)}",
        colour=colour,
    )
    embed.add_field(name="Lowest / highest", value=f"{currency}{book.lowest:.2f} / {currency}{book.highest:.2f}")
    embed.add_field(name="Category", value=book.category)
    embed.add_field(name="Rating", value=star_rating(book.rating))
    embed.add_field(name="Availability", value=availability)
    embed.add_field(name="Tracked since", value=f"<t:{_ts(book.first_seen)}:D>")
    embed.add_field(name="Last checked", value=f"<t:{_ts(book.last_seen)}:R>")

    # History: a mini chart of recent checks plus a list of the actual price changes.
    recent = [p.price for p in book.history[-SPARKLINE_POINTS:]]
    changes = book.price_changes()[-HISTORY_ROWS:]
    rows = [f"{p.scraped_at:%Y-%m-%d}  {currency + format(p.price, '.2f'):>9}" for p in reversed(changes)]
    checks = len(book.history)
    history = f"`{sparkline(recent)}`  {checks} check{'s' if checks != 1 else ''}\n```\n" + "\n".join(rows) + "\n```"
    embed.add_field(name="Price history (newest first)", value=history, inline=False)

    if other_matches:
        embed.add_field(
            name="Other matches",
            value="\n".join(f"• {truncate(t, 90)}" for t in other_matches[:5]),
            inline=False,
        )
    embed.set_footer(text="Data: book-price-tracker · checked daily")
    return embed


class Price(commands.Cog):
    def __init__(self, bot: UtilityBot) -> None:
        self.bot = bot
        self.repo = bot.prices

    @app_commands.command(name="price", description="Latest price and price history for a book")
    @app_commands.describe(title="Book title (start typing for suggestions)")
    @app_commands.checks.cooldown(1, 5.0, key=lambda i: i.user.id)
    async def price(self, interaction: discord.Interaction, title: app_commands.Range[str, 1, 200]) -> None:
        try:
            # File I/O, so run it off the event loop.
            result = await asyncio.to_thread(self.repo.find, title)
        except PriceDatabaseError as exc:
            log.warning("Price lookup failed: %s", exc)
            raise UserFacingError(str(exc)) from None

        if result.book is None:
            hint = ""
            if result.suggestions:
                hint = "\n\nDid you mean:\n" + "\n".join(f"• {s}" for s in result.suggestions)
            raise UserFacingError(f"I couldn't find a book called **{truncate(title, 100)}**.{hint}")

        embed = build_price_embed(result.book, self.bot.settings.currency_symbol, result.suggestions)
        await interaction.response.send_message(embed=embed)

    @price.autocomplete("title")
    async def _title_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        try:
            titles = await asyncio.to_thread(self.repo.search_titles, current, 25)
        except PriceDatabaseError:
            return []
        # Choice names/values are limited to 100 characters by Discord.
        return [app_commands.Choice(name=truncate(t, 100), value=t[:100]) for t in titles]


async def setup(bot: UtilityBot) -> None:
    await bot.add_cog(Price(bot))
