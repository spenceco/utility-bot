"""/stats: uptime, reach, command usage and a few health numbers."""

from __future__ import annotations

import platform
import resource
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from .. import __version__
from ..core.formatting import humanize_duration

if TYPE_CHECKING:
    from ..bot import UtilityBot


class Stats(commands.Cog):
    def __init__(self, bot: UtilityBot) -> None:
        self.bot = bot

    @app_commands.command(name="stats", description="Uptime, server count and command usage")
    @app_commands.checks.cooldown(1, 10.0, key=lambda i: i.user.id)
    async def stats(self, interaction: discord.Interaction) -> None:
        bot = self.bot
        uptime = discord.utils.utcnow() - bot.started_at
        members = sum(g.member_count or 0 for g in bot.guilds)
        # ru_maxrss is in kilobytes on Linux.
        peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024

        embed = discord.Embed(title="📈 utility-bot stats", colour=discord.Colour.teal())
        if bot.user:
            embed.set_thumbnail(url=bot.user.display_avatar.url)
        embed.add_field(name="Uptime", value=humanize_duration(uptime), inline=False)
        embed.add_field(name="Servers", value=f"{len(bot.guilds):,}")
        embed.add_field(name="Members reached", value=f"{members:,}")
        embed.add_field(name="Latency", value=f"{bot.latency * 1000:.0f} ms")
        # +1 counts this /stats call, which is only recorded after it finishes.
        embed.add_field(name="Commands (this session)", value=f"{bot.session_commands + 1:,}")
        embed.add_field(name="Commands (all time)", value=f"{bot.usage.total() + 1:,}")
        embed.add_field(name="Pending reminders", value=f"{bot.reminders.count_pending():,}")

        top = bot.usage.top(5)
        if top:
            embed.add_field(
                name="Most used",
                value="\n".join(f"`/{name}` · {uses:,}" for name, uses in top),
                inline=False,
            )
        embed.set_footer(
            text=f"v{__version__} · Python {platform.python_version()} · "
            f"discord.py {discord.__version__} · {peak_mb:.0f} MB peak memory"
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: UtilityBot) -> None:
    await bot.add_cog(Stats(bot))
