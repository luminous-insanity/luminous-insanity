
"""
Standings are calculated fresh from picks + final scores every time.
There is no running total to get out of sync.
"""

from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth.models import User

from api.models import Game
from api.rules import grade_pick
from .models import Pick
from .ranking import assign_ranks, rank_key, win_pct


@dataclass
class Standing:
    # Same attribute names the templates already use.
    user: User
    wins: int = 0
    losses: int = 0
    ties: int = 0
    # Added for the new leaderboard. All optional, so existing code that builds
    # or reads a Standing keeps working unchanged.
    pending: int = 0            # picks on games that aren't final yet
    rank: int = 0               # shared on ties: 1, 1, 3
    movement_kind: str = ""     # Weekly only: up / down / same / new / none
    movement_label: str = ""

    @property
    def completed(self):
        return self.wins + self.losses + self.ties

    @property
    def win_pct(self):
        """Display-only. None when the player has no completed games."""
        return win_pct(self.wins, self.losses, self.ties)

    @property
    def record(self):
        return (self.wins, self.losses, self.ties)


def _tally(picks, table):
    for pick in picks:
        result = grade_pick(
            pick.team_picked,
            pick.game.home_score,
            pick.game.away_score,
        )
        standing = table[pick.user_id]

        if result == "win":
            standing.wins += 1
        elif result == "loss":
            standing.losses += 1
        elif result == "tie":
            standing.ties += 1


def _final_picks(user_ids, season=None, week=None):
    if season is None:
        season = settings.NFL_SEASON

    picks = Pick.objects.filter(
        user_id__in=user_ids,
        game__season=season,
        game__status=Game.FINAL,
    )

    if week is not None:
        picks = picks.filter(game__week=week)

    return picks.select_related("game")


def _count_pending(table, season, week=None):
    """Picks that can't be graded yet. They are never counted as losses."""
    picks = Pick.objects.filter(
        user_id__in=table.keys(),
        game__season=season,
    ).exclude(
        game__status=Game.FINAL,
        game__home_score__isnull=False,
        game__away_score__isnull=False,
    )
    if week is not None:
        picks = picks.filter(game__week=week)
    for user_id in picks.values_list("user_id", flat=True):
        table[user_id].pending += 1


def compute_standings(week=None, season=None, users=None, with_pending=False):
    """Leaderboard: season-wide by default, or for one selected week.

    users:        limit the table to these users (default: every non-admin).
    with_pending: also count each player's not-yet-final picks.

    Order and ranking: most wins, then fewest losses, then most ties; players
    who are still level share a rank (1, 1, 3) and are listed alphabetically.
    """
    if season is None:
        season = settings.NFL_SEASON

    if users is None:
        users = User.objects.filter(is_superuser=False)
    users = list(users)
    table = {u.id: Standing(user=u) for u in users}

    _tally(_final_picks(table.keys(), season=season, week=week), table)
    if with_pending:
        _count_pending(table, season, week)

    rows = sorted(
        table.values(),
        key=lambda s: rank_key(s) + (s.user.username.lower(),),
    )
    return assign_ranks(rows)


def standing_for(user, week=None, season=None):
    """One person's record, season-wide by default or for one week."""
    if season is None:
        season = settings.NFL_SEASON

    table = {user.id: Standing(user=user)}

    _tally(_final_picks(table.keys(), season=season, week=week), table)

    return table[user.id]

