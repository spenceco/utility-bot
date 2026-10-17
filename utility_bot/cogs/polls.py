"""/poll: a button poll whose counts update live as people vote.

Buttons are "dynamic items": their custom_id encodes the poll and option
(e.g. "poll:12:3"), and the votes live in SQLite. So the buttons keep working
after the bot restarts, with no in-memory state to lose.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from ..core.formatting import truncate
from ..core.polls import Poll, PollError, VoteResult, parse_options, validate_question
from ..errors import UserFacingError

if TYPE_CHECKING:
    from ..bot import UtilityBot

log = logging.getLogger(__name__)

OPEN_COLOUR = discord.Colour.blurple()
CLOSED_COLOUR = discord.Colour.dark_grey()

# Button clicks get their own cooldown: 4 clicks per 5 seconds per user.
_click_cooldown = commands.CooldownMapping.from_cooldown(4, 5.0, lambda i: i.user.id)


def build_poll_embed(poll: Poll) -> discord.Embed:
    icon = "🔒" if poll.closed else "📊"
    embed = discord.Embed(
        title=truncate(f"{icon} {poll.question}", 256),
        description=f"Started by <@{poll.author_id}>\n\n{poll.results_text()}",
        colour=CLOSED_COLOUR if poll.closed else OPEN_COLOUR,
    )
    total = poll.total_votes
    votes = f"{total} vote{'s' if total != 1 else ''}"
    if poll.closed:
        winners = poll.winners()
        if not winners:
            result = "No votes were cast."
        elif len(winners) == 1:
            result = f"🏆 **{winners[0]}** wins!"
        else:
            result = "🤝 Tie between " + ", ".join(f"**{w}**" for w in winners)
        embed.add_field(name="Final result", value=result, inline=False)
        embed.set_footer(text=f"Poll #{poll.id} · closed · {votes}")
    else:
        embed.set_footer(text=f"Poll #{poll.id} · {votes} · click to vote, click again to undo")
    return embed


def build_poll_view(poll: Poll) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    counts = poll.tally()
    for index, (option, count) in enumerate(zip(poll.options, counts)):
        view.add_item(
            PollVoteButton(
                poll.id, index, label=f"{option} · {count}", row=index // 5, disabled=poll.closed
            )
        )
    if not poll.closed:
        view.add_item(PollCloseButton(poll.id))
    return view


class PollVoteButton(
    discord.ui.DynamicItem[discord.ui.Button], template=r"poll:(?P<poll_id>\d+):(?P<option>\d+)"
):
    def __init__(
        self, poll_id: int, option: int, *, label: str = "Vote", row: int | None = None, disabled: bool = False
    ) -> None:
        super().__init__(
            discord.ui.Button(
                label=truncate(label, 80),
                style=discord.ButtonStyle.primary,
                custom_id=f"poll:{poll_id}:{option}",
                row=row,
                disabled=disabled,
            )
        )
        self.poll_id = poll_id
        self.option = option

    @classmethod
    async def from_custom_id(
        cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str]
    ) -> PollVoteButton:
        return cls(int(match["poll_id"]), int(match["option"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        bot: UtilityBot = interaction.client  # type: ignore[assignment]
        retry_after = _click_cooldown.get_bucket(interaction).update_rate_limit()
        if retry_after:
            await interaction.response.send_message(
                f"⏳ You're clicking fast! Try again in {retry_after:.0f}s.", ephemeral=True
            )
            return

        poll = bot.polls.get(self.poll_id)
        if poll is None or poll.closed or not 0 <= self.option < len(poll.options):
            await interaction.response.send_message("This poll has ended.", ephemeral=True)
            return

        result = bot.polls.vote(poll.id, interaction.user.id, self.option)
        poll = bot.polls.get(poll.id)
        assert poll is not None
        await interaction.response.edit_message(embed=build_poll_embed(poll), view=build_poll_view(poll))

        choice = poll.options[self.option]
        feedback = {
            VoteResult.ADDED: f"✅ You voted for **{choice}**.",
            VoteResult.CHANGED: f"🔄 Vote changed to **{choice}**.",
            VoteResult.REMOVED: f"↩️ Vote for **{choice}** removed.",
        }[result]
        await interaction.followup.send(feedback, ephemeral=True)


class PollCloseButton(discord.ui.DynamicItem[discord.ui.Button], template=r"poll-close:(?P<poll_id>\d+)"):
    def __init__(self, poll_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                label="End poll", emoji="🔒", style=discord.ButtonStyle.secondary,
                custom_id=f"poll-close:{poll_id}", row=2,
            )
        )
        self.poll_id = poll_id

    @classmethod
    async def from_custom_id(
        cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str]
    ) -> PollCloseButton:
        return cls(int(match["poll_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        bot: UtilityBot = interaction.client  # type: ignore[assignment]
        poll = bot.polls.get(self.poll_id)
        if poll is None or poll.closed:
            await interaction.response.send_message("This poll has already ended.", ephemeral=True)
            return

        # Only the poll's creator or a moderator may end it.
        perms = getattr(interaction.user, "guild_permissions", None)
        if interaction.user.id != poll.author_id and not (perms and perms.manage_messages):
            await interaction.response.send_message(
                "Only the person who started this poll (or a moderator) can end it.", ephemeral=True
            )
            return

        bot.polls.close(poll.id)
        poll.closed = True
        await interaction.response.edit_message(embed=build_poll_embed(poll), view=build_poll_view(poll))


class Polls(commands.Cog):
    def __init__(self, bot: UtilityBot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        # Teach the bot to recognise poll buttons on any message, even old ones.
        self.bot.add_dynamic_items(PollVoteButton, PollCloseButton)

    async def cog_unload(self) -> None:
        self.bot.remove_dynamic_items(PollVoteButton, PollCloseButton)

    @app_commands.command(name="poll", description="Start a button poll with live vote counts")
    @app_commands.describe(
        question="What are you asking?",
        options="2-10 choices separated by commas, e.g. Pizza, Tacos, Sushi",
    )
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 30.0, key=lambda i: i.user.id)
    async def poll(self, interaction: discord.Interaction, question: str, options: str) -> None:
        try:
            question = validate_question(question)
            choices = parse_options(options)
        except PollError as exc:
            raise UserFacingError(str(exc)) from None

        poll = self.bot.polls.create(
            guild_id=interaction.guild_id,
            channel_id=interaction.channel_id,
            author_id=interaction.user.id,
            question=question,
            options=choices,
            created_at=int(discord.utils.utcnow().timestamp()),
        )
        await interaction.response.send_message(embed=build_poll_embed(poll), view=build_poll_view(poll))
        message = await interaction.original_response()
        self.bot.polls.set_message_id(poll.id, message.id)
        log.info("Poll #%s created in guild %s with %d options", poll.id, poll.guild_id, len(choices))


async def setup(bot: UtilityBot) -> None:
    await bot.add_cog(Polls(bot))
