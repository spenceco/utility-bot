import pytest

from utility_bot.core.polls import (
    MAX_OPTIONS,
    PollError,
    PollStore,
    VoteResult,
    parse_options,
    validate_question,
)


def test_parse_options_separators() -> None:
    assert parse_options("Pizza, Tacos, Sushi") == ["Pizza", "Tacos", "Sushi"]
    assert parse_options("Yes, definitely | No") == ["Yes, definitely", "No"]
    assert parse_options("a; b") == ["a", "b"]


def test_parse_options_cleans_and_dedupes() -> None:
    assert parse_options("  Red ,, red, Blue  ,  ") == ["Red", "Blue"]
    assert parse_options("New   York, Paris") == ["New York", "Paris"]


@pytest.mark.parametrize("raw", ["just one", "a, a", ",".join(str(i) for i in range(MAX_OPTIONS + 1)), "x" * 60 + ", b"])
def test_parse_options_rejects(raw: str) -> None:
    with pytest.raises(PollError):
        parse_options(raw)


def test_validate_question() -> None:
    assert validate_question("  Lunch?  ") == "Lunch?"
    with pytest.raises(PollError):
        validate_question("   ")
    with pytest.raises(PollError):
        validate_question("?" * 300)


def _poll(store: PollStore):
    return store.create(guild_id=1, channel_id=2, author_id=3, question="Lunch?", options=["A", "B", "C"], created_at=0)


def test_vote_add_change_remove(bot_db) -> None:
    store = PollStore(bot_db)
    poll = _poll(store)
    assert store.vote(poll.id, user_id=10, option=0) is VoteResult.ADDED
    assert store.vote(poll.id, user_id=10, option=1) is VoteResult.CHANGED
    assert store.get(poll.id).tally() == [0, 1, 0]
    assert store.vote(poll.id, user_id=10, option=1) is VoteResult.REMOVED
    assert store.get(poll.id).total_votes == 0


def test_tally_winners_and_text(bot_db) -> None:
    store = PollStore(bot_db)
    poll = _poll(store)
    for user, option in [(1, 0), (2, 0), (3, 1)]:
        store.vote(poll.id, user, option)
    poll = store.get(poll.id)
    assert poll.tally() == [2, 1, 0]
    assert poll.winners() == ["A"]
    text = poll.results_text()
    assert "2 votes (67%)" in text and "1 vote (33%)" in text and "0 votes (0%)" in text

    store.vote(poll.id, 4, 1)
    assert store.get(poll.id).winners() == ["A", "B"]  # tie


def test_no_votes_no_winner(bot_db) -> None:
    store = PollStore(bot_db)
    assert _poll(store).winners() == []


def test_close_and_message_id(bot_db) -> None:
    store = PollStore(bot_db)
    poll = _poll(store)
    store.set_message_id(poll.id, 999)
    store.close(poll.id)
    loaded = store.get(poll.id)
    assert loaded.closed and loaded.message_id == 999
    assert store.get(12345) is None
