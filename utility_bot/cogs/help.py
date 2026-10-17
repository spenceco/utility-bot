"""/help: an embed listing every command, built from the live command tree.

Because the list is generated from the registered commands, it can't drift
out of date when a command is added or renamed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from ..bot import UtilityBot

# A worked example for each command, shown under its description.
EXAMPLES: dict[str, str] = {
    "remind": "/remind time:2h message:Take the bread out",
    "reminders list": "/reminders list",
    "reminders cancel": "/reminders cancel reminder_id:3",
    "poll": "/poll question:Lunch? options:Pizza, Tacos, Sushi",
    "price": "/price title:Sapiens",
    "stats": "/stats",
    "help": "/help",
}


def _signature(command: app_commands.Command) -> str:
    params = " ".join(
        f"<{p.display_name}>" if p.required else f"[{p.display_name}]" for p in command.parameters
    )
    return f"/{command.qualified_name} {params}".strip()


def iter_commands(tree: app_commands.CommandTree) -> list[app_commands.Command]:
    """All slash commands, with groups expanded into their subcommands."""
    found: list[app_commands.Command] = []
    for command in sorted(tree.get_commands(), key=lambda c: c.name):
        if isinstance(command, app_commands.Group):
            found.extend(sorted(command.commands, key=lambda c: c.name))  # type: ignore[arg-type]
        elif isinstance(command, app_commands.Command):
            found.append(command)
    return found


class Help(commands.Cog):
    def __init__(self, bot: UtilityBot) -> None:
        self.bot = bot

    @app_commands.command(name="help", description="List everything I can do")
    @app_commands.checks.cooldown(1, 5.0, key=lambda i: i.user.id)
    async def help(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="🧰 utility-bot commands",
            description="Reminders, polls and book prices. Options autocomplete as you type.",
            colour=discord.Colour.blurple(),
        )
        for command in iter_commands(self.bot.tree):
            value = command.description
            example = EXAMPLES.get(command.qualified_name)
            if example:
                value += f"\n`{example}`"
            embed.add_field(name=_signature(command), value=value, inline=False)
        embed.set_footer(text="<required>  [optional] · replies marked 'Only you can see this' are private")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: UtilityBot) -> None:
    await bot.add_cog(Help(bot))
