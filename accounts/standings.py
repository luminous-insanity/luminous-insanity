# accounts/standings.py
"""
Standings are calculated fresh from picks + final scores every time.
There is no running total to get out of sync, so:
  * running the score update twice can't double count
  * a pick entered after the score arrived still counts
  * a corrected score fixes everyone's record automatically
"""
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth.models import User

from api.models import Game
from api.rules import grade_pick
from .models import Pick


@dataclass
class Standing:
    # Same attribute names the templates already use: stat.user, stat.wins, ...
    user: User
    wins: int = 0
    losses: int = 0
    ties: int = 0


def _tally(picks, table):
    for pick in picks:
        result = grade_pick(pick.team_picked, pick.game.home_score, pick.game.away_score)
        standing = table[pick.user_id]
        if result == "win":
            standing.wins += 1
        elif result == "loss":
            standing.losses += 1
        elif result == "tie":
            standing.ties += 1


def _final_picks(user_ids):
    return (Pick.objects
            .filter(user_id__in=user_ids,
                    game__season=settings.NFL_SEASON,
                    game__status=Game.FINAL)
            .select_related("game"))


def compute_standings():
    """Leaderboard: everyone except admin/superuser accounts, best first."""
    users = list(User.objects.filter(is_superuser=False))
    table = {u.id: Standing(user=u) for u in users}
    _tally(_final_picks(table.keys()), table)
    return sorted(table.values(),
                  key=lambda s: (-s.wins, s.losses, s.user.username.lower()))


def standing_for(user):
    """One person's record (works for any account, including admins)."""
    table = {user.id: Standing(user=user)}
    _tally(_final_picks(table.keys()), table)
    return table[user.id]
