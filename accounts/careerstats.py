"""
Lifetime stats for every player: weeks won, seasons won, overall record.

Worked out from picks and final scores (never stored), using the same rules as
the leaderboard:
  * Week winner: top of a COMPLETED week (most wins, then fewest losses, then
    most ties), with at least one win. Players tied for first all count.
  * Season champion: top of a FINALIZED season by the same rules. Co-champions
    all count.
One database query reads every graded pick, so asking for everybody at once
costs the same as asking for one person. Call career_stats() once per request.
"""
from collections import defaultdict
from dataclasses import dataclass

from django.db.models import Count, Q

from api.models import Game
from api.rules import grade_pick

from .leaderboard import season_is_finalized
from .models import Pick
from .ranking import win_pct

_INDEX = {"win": 0, "loss": 1, "tie": 2}


@dataclass
class Career:
    weeks_won: int = 0
    seasons_won: int = 0
    wins: int = 0
    losses: int = 0
    ties: int = 0

    @property
    def completed(self):
        return self.wins + self.losses + self.ties

    @property
    def win_pct(self):
        return win_pct(self.wins, self.losses, self.ties)


def _best(table, need_wins):
    """Users tied for first in {user_id: [w, l, t]} (empty if nobody qualifies)."""
    if not table:
        return []
    key = lambda rec: (-rec[0], rec[1], -rec[2])
    top = min(key(rec) for rec in table.values())
    winners = [uid for uid, rec in table.items() if key(rec) == top]
    if need_wins and table[winners[0]][0] == 0:
        return []
    return winners


def career_stats():
    """{user_id: Career} for every player who has ever made a graded pick."""
    by_week = defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))
    by_season = defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))
    career = defaultdict(Career)

    graded = Pick.objects.filter(
        game__status=Game.FINAL,
        game__home_score__isnull=False,
        game__away_score__isnull=False,
    ).values_list(
        "user_id", "game__season", "game__week",
        "team_picked", "game__home_score", "game__away_score",
    )
    for user_id, season, week, picked, home, away in graded:
        result = grade_pick(picked, home, away)
        if result not in _INDEX:
            continue
        i = _INDEX[result]
        by_week[(season, week)][user_id][i] += 1
        by_season[season][user_id][i] += 1
        record = career[user_id]
        if i == 0:
            record.wins += 1
        elif i == 1:
            record.losses += 1
        else:
            record.ties += 1

    # A week only counts once every game in it is final.
    weeks = Game.objects.order_by().values("season", "week").annotate(
        total=Count("id"),
        done=Count("id", filter=Q(status=Game.FINAL)),
    )
    for row in weeks:
        if row["total"] and row["total"] == row["done"]:
            table = by_week.get((row["season"], row["week"]), {})
            for user_id in _best(table, need_wins=True):
                career[user_id].weeks_won += 1

    for season, table in by_season.items():
        if season_is_finalized(season):
            for user_id in _best(table, need_wins=False):
                career[user_id].seasons_won += 1

    return career


def career_for(stats, user_id):
    """Safe lookup: players with no graded picks get an empty Career."""
    return stats.get(user_id) or Career()
