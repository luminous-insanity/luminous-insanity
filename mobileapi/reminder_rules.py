"""Pure rules for the weekly pick reminder. No Django in here on purpose.

Rule (as specified): the first game day of the week (normally Thursday) is the
relevant one. Two hours before that day's first kickoff, remind every player
who has not yet picked ALL of that day's games. Everything is computed from
absolute instants, so it is correct in any time zone, and it is recomputed from
the current schedule on every run, so a moved kickoff moves the reminder.
"""
from datetime import timedelta
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")
LEAD = timedelta(hours=2)


def first_day_games(entries):
    """entries: iterable of (game_id, lock_at aware datetime or None).

    Returns (first_lock, [game_ids]) for the first Eastern calendar day that
    has games, or None. Games with no lock time are ignored.
    """
    known = [(game_id, lock) for game_id, lock in entries if lock is not None]
    if not known:
        return None
    first_day = min(lock.astimezone(EASTERN).date() for _, lock in known)
    day = [(g, t) for g, t in known if t.astimezone(EASTERN).date() == first_day]
    return min(t for _, t in day), [g for g, _ in day]


def reminder_due(first_lock, now):
    """True from two hours before the first kickoff until that kickoff."""
    return first_lock - LEAD <= now < first_lock


def reminder_text(first_lock):
    day = first_lock.astimezone(EASTERN).strftime("%A")
    return (
        "Picks due soon \U0001F3C8",
        f"{day}'s first game kicks off in about 2 hours. Make your picks now!",
    )
