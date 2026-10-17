"""One place that turns every slash-command error into a friendly reply.

Commands raise UserFacingError("...") for problems the user can fix (bad
input, nothing found). Anything unexpected is logged with a full traceback
and the user just sees a short apology, never a stack trace.
"""

from __future__ import annotations

import logging
import math

import discord
from discord import app_commands

log = logging.getLogger(__name__)

ERROR_COLOUR = discord.Colour.red()


class UserFacingError(app_commands.AppCommandError):
    """An error whose message is safe and helpful to show to the user."""


def error_embed(message: str, title: str = "Hmm, that didn't work") -> discord.Embed:
    return discord.Embed(title=title, description=message, colour=ERROR_COLOUR)


async def send_ephemeral(interaction: discord.Interaction, embed: discord.Embed) -> None:
    """Reply privately, whether or not the interaction was already answered."""
    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except discord.HTTPException:
        log.warning("Could not send error message for interaction %s", interaction.id)


def describe_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> str | None:
    """User-facing text for known errors, or None if it's an unexpected bug."""
    if isinstance(error, app_commands.CommandInvokeError) and isinstance(
        error.original, app_commands.AppCommandError
    ):
        error = error.original

    command = f"/{interaction.command.qualified_name}" if interaction.command else "that command"

    if isinstance(error, UserFacingError):
        return str(error)
    if isinstance(error, app_commands.CommandOnCooldown):
        wait = math.ceil(error.retry_after)
        return f"⏳ Slow down! You can use `{command}` again in {wait} second{'s' if wait != 1 else ''}."
    if isinstance(error, app_commands.NoPrivateMessage):
        return "This command only works inside a server, not in DMs."
    if isinstance(error, app_commands.MissingPermissions):
        return "You need the " + ", ".join(error.missing_permissions) + " permission to do that."
    if isinstance(error, app_commands.BotMissingPermissions):
        return "I'm missing the " + ", ".join(error.missing_permissions) + " permission in this channel."
    if isinstance(error, app_commands.TransformerError):
        return f"I couldn't understand `{error.value}` for that option."
    if isinstance(error, app_commands.CheckFailure):
        return "You can't use that command here."
    return None


async def handle_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    """Registered as CommandTree.on_error in bot.py."""
    message = describe_error(interaction, error)
    if message is None:
        name = interaction.command.qualified_name if interaction.command else "?"
        log.error("Unhandled error in /%s", name, exc_info=error)
        message = "Something went wrong on my side. It's been logged and I'll look into it."
    await send_ephemeral(interaction, error_embed(message))
