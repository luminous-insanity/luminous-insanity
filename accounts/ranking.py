"""
Pure ranking rules for the leaderboard. No Django in here on purpose, so the
rules can be tested on their own and read in one place.

Ranking:  most wins, then fewest losses, then most ties.
Players who are still level share a rank and the next rank is skipped
(1, 1, 3). Winning percentage is for display only; it never decides rank.
"""


def rank_key(row):
    return (-row.wins, row.losses, -row.ties)


def assign_ranks(rows):
    """Set row.rank on rows that are already sorted best-first."""
    previous_key = None
    rank = 0
    for position, row in enumerate(rows, start=1):
        key = rank_key(row)
        if key != previous_key:
            rank = position
            previous_key = key
        row.rank = rank
    return rows


def win_pct(wins, losses, ties):
    """(wins + 0.5 * ties) / completed games * 100, or None with no completed games."""
    completed = wins + losses + ties
    if completed == 0:
        return None
    return (wins + 0.5 * ties) / completed * 100


def format_pct(value):
    return "—" if value is None else f"{value:.1f}%"


def movement(current_rank, previous_rank, week):
    """
    (kind, label) for the Weekly rank-movement badge.
      Week 1            -> ("none", "—")     no previous week exists
      no previous rank  -> ("new", "New")
      moved up 3        -> ("up", "↑3")
      moved down 2      -> ("down", "↓2")
      unchanged         -> ("same", "—0")
    """
    if week is None or week <= 1:
        return ("none", "—")
    if previous_rank is None:
        return ("new", "New")
    change = previous_rank - current_rank
    if change > 0:
        return ("up", f"↑{change}")
    if change < 0:
        return ("down", f"↓{-change}")
    return ("same", "—0")


def _plural(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def record_gap(mine, theirs):
    """
    Plain-English season gap between two (wins, losses, ties) records, using the
    same order as the leaderboard: wins, then losses, then ties.
    Returns (who, text) where who is "me", "them" or "tied".
    """
    my_w, my_l, my_t = mine
    th_w, th_l, th_t = theirs
    if mine == theirs:
        return ("tied", "You're tied on the season")
    if my_w != th_w:
        diff = abs(my_w - th_w)
        if my_w > th_w:
            return ("me", f"You lead by {_plural(diff, 'win')}")
        return ("them", f"You trail by {_plural(diff, 'win')}")
    if my_l != th_l:
        diff = abs(my_l - th_l)
        if my_l < th_l:
            return ("me", f"Level on wins; you have {_plural(diff, 'fewer loss')}".replace("fewer losss", "fewer losses"))
        return ("them", f"Level on wins; you have {_plural(diff, 'more loss')}".replace("more losss", "more losses"))
    diff = abs(my_t - th_t)
    if my_t > th_t:
        return ("me", f"Level on wins and losses; you have {_plural(diff, 'more tie')}")
    return ("them", f"Level on wins and losses; you have {_plural(diff, 'fewer tie')}")
