from utility_bot.core.reminders import ReminderStore


def _add(store: ReminderStore, user: int, due: int, msg: str = "hi"):
    return store.add(user_id=user, channel_id=10, guild_id=20, message=msg, created_at=0, due_at=due)


def test_add_and_list(bot_db) -> None:
    store = ReminderStore(bot_db)
    later = _add(store, 1, 200, "later")
    sooner = _add(store, 1, 100, "sooner")
    _add(store, 2, 50, "someone else")
    assert [r.id for r in store.for_user(1)] == [sooner.id, later.id]  # sorted by due time
    assert store.count_for_user(1) == 2
    assert store.count_pending() == 3


def test_due_only_returns_expired(bot_db) -> None:
    store = ReminderStore(bot_db)
    _add(store, 1, 100)
    _add(store, 1, 300)
    assert [r.due_at for r in store.due(now=150)] == [100]
    assert store.due(now=50) == []


def test_cancel_checks_ownership(bot_db) -> None:
    store = ReminderStore(bot_db)
    reminder = _add(store, 1, 100)
    assert store.cancel(reminder.id, user_id=2) is False  # not yours
    assert store.cancel(reminder.id, user_id=1) is True
    assert store.cancel(reminder.id, user_id=1) is False  # already gone


def test_survives_reconnect(tmp_path) -> None:
    """The whole point: reminders are still there after a restart."""
    from utility_bot.core.database import connect

    path = tmp_path / "bot.db"
    conn = connect(path)
    _add(ReminderStore(conn), 1, 100, "persist me")
    conn.close()

    conn = connect(path)
    assert [r.message for r in ReminderStore(conn).due(now=1000)] == ["persist me"]
    conn.close()
