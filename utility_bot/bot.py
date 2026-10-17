"""The bot class: owns the database, loads the cogs and syncs slash commands."""

from __future__ import annotations

import asyncio
import logging
import signal

import discord
from discord import app_commands
from discord.ext import commands

from .config import Settings
from .core.database import connect
from .core.polls import PollStore
from .core.prices import PriceRepository
from .core.reminders import ReminderStore
from .core.usage import UsageStore
from .errors import handle_app_command_error

log = logging.getLogger(__name__)

# Each feature lives in its own cog module under utility_bot/cogs.
EXTENSIONS = (
    "utility_bot.cogs.reminders",
    "utility_bot.cogs.polls",
    "utility_bot.cogs.price",
    "utility_bot.cogs.stats",
    "utility_bot.cogs.help",
)

# View Channel + Send Messages + Embed Links + Read Message History.
INVITE_PERMISSIONS = discord.Permissions(
    view_channel=True, send_messages=True, embed_links=True, read_message_history=True
)


# This bot never joins voice, so skip the "voice will NOT be supported" warnings.
discord.VoiceClient.warn_nacl = False
if hasattr(discord.VoiceClient, "warn_dave"):
    discord.VoiceClient.warn_dave = False


class UtilityBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        # Slash commands need no privileged intents (no message content, no member list).
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=discord.Intents.default(),
            help_command=None,
            activity=discord.Activity(type=discord.ActivityType.listening, name="/help"),
        )
        self.settings = settings
        self.started_at = discord.utils.utcnow()
        self.session_commands = 0

        self.db = connect(settings.bot_db_path)
        self.reminders = ReminderStore(self.db)
        self.polls = PollStore(self.db)
        self.usage = UsageStore(self.db)
        self.prices = PriceRepository(settings.price_db_path)

        self.tree.on_error = handle_app_command_error

    async def setup_hook(self) -> None:
        """Runs once, after login and before connecting to the gateway."""
        for extension in EXTENSIONS:
            await self.load_extension(extension)
            log.info("Loaded %s", extension)

        # systemd stops services with SIGTERM; shut down cleanly instead of dying mid-write.
        loop = asyncio.get_running_loop()
        try:
            loop.add_signal_handler(signal.SIGTERM, lambda: asyncio.create_task(self.close()))
        except NotImplementedError:  # e.g. Windows
            pass

        await self.sync_commands()

    async def sync_commands(self) -> None:
        """Register slash commands with Discord.

        With DEV_GUILD_ID set, commands go to that one server and show up
        instantly (handy while developing). Otherwise they're registered globally.
        """
        if self.settings.dev_guild_id:
            guild = discord.Object(id=self.settings.dev_guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("Synced %d commands to dev guild %s", len(synced), guild.id)
        else:
            synced = await self.tree.sync()
            log.info("Synced %d global commands", len(synced))

    async def on_ready(self) -> None:
        assert self.user is not None
        log.info("Logged in as %s (id %s) in %d servers", self.user, self.user.id, len(self.guilds))
        invite = discord.utils.oauth_url(
            self.user.id, permissions=INVITE_PERMISSIONS, scopes=("bot", "applications.commands")
        )
        log.info("Invite link: %s", invite)

    async def on_app_command_completion(
        self, interaction: discord.Interaction, command: app_commands.Command | app_commands.ContextMenu
    ) -> None:
        """Count every successful command for /stats."""
        self.session_commands += 1
        self.usage.record(command.qualified_name)
        log.info("/%s used by %s in guild %s", command.qualified_name, interaction.user.id, interaction.guild_id)

    async def close(self) -> None:
        log.info("Shutting down")
        await super().close()
        self.db.close()
