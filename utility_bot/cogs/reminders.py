"""/remind, /reminders list and /reminders cancel, plus the delivery loop.

Reminders are written to SQLite the moment they're created. A background
task checks every few seconds for reminders that are due, so if the bot was
offline it simply delivers the overdue ones (marked "late") when it's back.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from ..core.formatting import humanize_duration, truncate
from ..core.reminders import MAX_ACTIVE_PER_USER, MAX_MESSAGE_LENGTH, Reminder
from ..core.timeparse import TimeParseError, parse_duration, validate_reminder_delay
from ..errors import UserFacingError

if TYPE_CHECKING:
    from ..bot import UtilityBot

log = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 5
LATE_THRESHOLD_SECONDS = 60  # flag reminders delivered more than this late
REMINDER_COLOUR = discord.Colour.gold()


def _now() -> int:
    return int(discord.utils.utcnow().timestamp())


class Reminders(commands.Cog):
    def __init__(self, bot: UtilityBot) -> None:
        self.bot = bot
        self.store = bot.reminders

    async def cog_load(self) -> None:
        self.deliver_due.start()

    async def cog_unload(self) -> None:
        self.deliver_due.cancel()

    # ---- commands ---------------------------------------------------------

    @app_commands.command(name="remind", description="Set a reminder, e.g. time: 10m  message: stretch")
    @app_commands.describe(
        time="When to remind you: 30s, 10m, 2h, 1d 4h, 1w …",
        message="What should I remind you about?",
    )
    @app_commands.checks.cooldown(1, 5.0, key=lambda i: i.user.id)
    async def remind(
        self,
        interaction: discord.Interaction,
        time: str,
        message: app_commands.Range[str, 1, MAX_MESSAGE_LENGTH],
    ) -> None:
        try:
            delay = parse_duration(time)
            validate_reminder_delay(delay)
        except TimeParseError as exc:
            raise UserFacingError(str(exc)) from None

        if self.store.count_for_user(interaction.user.id) >= MAX_ACTIVE_PER_USER:
            raise UserFacingError(
                f"You already have {MAX_ACTIVE_PER_USER} reminders. "
                "Cancel one with `/reminders cancel` first."
            )

        now = _now()
        reminder = self.store.add(
            user_id=interaction.user.id,
            channel_id=interaction.channel_id,
            guild_id=interaction.guild_id,
            message=message,
            created_at=now,
            due_at=now + int(delay.total_seconds()),
        )

        embed = discord.Embed(title="⏰ Reminder set", description=message, colour=REMINDER_COLOUR)
        embed.add_field(
            name="When",
            value=f"<t:{reminder.due_at}:F>\n(<t:{reminder.due_at}:R>, in {humanize_duration(delay)})",
        )
        embed.set_footer(text=f"Reminder #{reminder.id} · cancel with /reminders cancel")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    reminders_group = app_commands.Group(name="reminders", description="See or cancel your reminders")

    @reminders_group.command(name="list", description="Show your upcoming reminders")
    @app_commands.checks.cooldown(1, 5.0, key=lambda i: i.user.id)
    async def list_reminders(self, interaction: discord.Interaction) -> None:
        reminders = self.store.for_user(interaction.user.id)
        if not reminders:
            raise UserFacingError("You have no upcoming reminders. Set one with `/remind`.")

        lines = [
            f"`#{r.id}` <t:{r.due_at}:R> — {truncate(r.message, 80)}" for r in reminders[:20]
        ]
        if len(reminders) > 20:
            lines.append(f"…and {len(reminders) - 20} more")
        embed = discord.Embed(
            title=f"Your reminders ({len(reminders)})", description="\n".join(lines), colour=REMINDER_COLOUR
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @reminders_group.command(name="cancel", description="Cancel one of your reminders")
    @app_commands.describe(reminder_id="The reminder number (start typing to pick from a list)")
    @app_commands.checks.cooldown(2, 5.0, key=lambda i: i.user.id)
    async def cancel_reminder(self, interaction: discord.Interaction, reminder_id: int) -> None:
        if not self.store.cancel(reminder_id, interaction.user.id):
            raise UserFacingError(f"You don't have a reminder #{reminder_id}. See `/reminders list`.")
        await interaction.response.send_message(f"🗑️ Reminder #{reminder_id} cancelled.", ephemeral=True)

    @cancel_reminder.autocomplete("reminder_id")
    async def _cancel_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[int]]:
        choices = []
        for r in self.store.for_user(interaction.user.id):
            label = f"#{r.id} · {truncate(r.message, 70)}"
            if current in str(r.id) or current.lower() in r.message.lower():
                choices.append(app_commands.Choice(name=label, value=r.id))
        return choices[:25]

    # ---- delivery ---------------------------------------------------------

    @tasks.loop(seconds=CHECK_INTERVAL_SECONDS)
    async def deliver_due(self) -> None:
        try:
            now = _now()
            for reminder in self.store.due(now):
                if await self._deliver(reminder, now):
                    self.store.delete(reminder.id)
        except Exception:  # never let one bad reminder kill the loop
            log.exception("Reminder delivery loop failed")

    @deliver_due.before_loop
    async def _wait_until_ready(self) -> None:
        await self.bot.wait_until_ready()

    def _reminder_embed(self, reminder: Reminder, now: int) -> discord.Embed:
        embed = discord.Embed(title="⏰ Reminder", description=reminder.message, colour=REMINDER_COLOUR)
        embed.add_field(name="Set", value=f"<t:{reminder.created_at}:R>")
        if now - reminder.due_at > LATE_THRESHOLD_SECONDS:
            embed.set_footer(text="Delivered late, sorry: I was offline when this was due.")
        return embed

    async def _deliver(self, reminder: Reminder, now: int) -> bool:
        """Send a reminder. Returns False only for temporary failures (retry later)."""
        embed = self._reminder_embed(reminder, now)
        # Only ever ping the reminder's owner, even if the text contains @everyone.
        mentions = discord.AllowedMentions(everyone=False, roles=False, users=[discord.Object(reminder.user_id)])

        try:
            channel = self.bot.get_channel(reminder.channel_id) or await self.bot.fetch_channel(
                reminder.channel_id
            )
            await channel.send(content=f"<@{reminder.user_id}>", embed=embed, allowed_mentions=mentions)
            return True
        except (discord.DiscordServerError, aiohttp.ClientError, asyncio.TimeoutError):
            log.warning("Temporary error delivering reminder %s; will retry", reminder.id)
            return False
        except (discord.Forbidden, discord.NotFound, discord.HTTPException, AttributeError):
            pass  # channel gone or no access: fall back to a DM below

        try:
            user = self.bot.get_user(reminder.user_id) or await self.bot.fetch_user(reminder.user_id)
            await user.send(embed=embed)
        except (discord.DiscordServerError, aiohttp.ClientError, asyncio.TimeoutError):
            return False
        except discord.HTTPException:
            log.warning("Could not deliver reminder %s to user %s", reminder.id, reminder.user_id)
        return True


async def setup(bot: UtilityBot) -> None:
    await bot.add_cog(Reminders(bot))
