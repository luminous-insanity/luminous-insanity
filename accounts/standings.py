
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


@dataclass
class Standing:
    # Same attribute names the templates already use.
    user: User
    wins: int = 0
    losses: int = 0
    ties: int = 0


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


def compute_standings(week=None, season=None):
    """Leaderboard: season-wide by default, or for one selected week."""
    if season is None:
        season = settings.NFL_SEASON

    users = list(User.objects.filter(is_superuser=False))
    table = {u.id: Standing(user=u) for u in users}

    _tally(_final_picks(table.keys(), season=season, week=week), table)

    return sorted(
        table.values(),
        key=lambda s: (
            -s.wins,
            s.losses,
            s.user.username.lower(),
        ),
    )


def standing_for(user, week=None, season=None):
    """One person's record, season-wide by default or for one week."""
    if season is None:
        season = settings.NFL_SEASON

    table = {user.id: Standing(user=user)}

    _tally(_final_picks(table.keys(), season=season, week=week), table)

    return table[user.id]

