"""
CROSSFIRE — hunt another player's pick on a specific game.

Core idea
---------
Each week you get a small number of Crossfire tokens. You aim one at another
player's pick on a game where you took the opposite side. When the game goes
final:

  * HIT  — you were right, they were wrong
  * MISS — you were wrong, they were right
  * PUSH — tie, or either pick not gradable

Crossfire never touches W-L-T standings, confidence points, or playoffs.
Outcomes are derived from final scores the same way standings are.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Optional

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count

from api.models import Game
from api.rules import grade_pick
from api.services import current_week

from .leaderboard import friend_users
from .models import Crossfire, Pick

# Policy knobs
TOKENS_PER_WEEK = 3
MAX_HUNTED_BOARD = 12
MAX_RECENT_HITS = 20


class CrossfireError(ValueError):
    """User-facing placement error."""


@dataclass
class GradedCrossfire:
    crossfire: Crossfire
    result: str  # 'hit' | 'miss' | 'push' | 'pending'
    game_final: bool


def tokens_used(user, season: int, week: int) -> int:
    return Crossfire.objects.filter(
        attacker=user, season=season, week=week
    ).count()


def tokens_left(user, season: int, week: int) -> int:
    return max(0, TOKENS_PER_WEEK - tokens_used(user, season, week))


def grade_crossfire(cf: Crossfire, game: Optional[Game] = None) -> GradedCrossfire:
    game = game or cf.game
    if not game.is_final:
        return GradedCrossfire(cf, 'pending', False)
    atk = grade_pick(cf.attacker_side, game.home_score, game.away_score)
    tgt = grade_pick(cf.target_side, game.home_score, game.away_score)
    if atk is None or tgt is None or atk == 'tie' or tgt == 'tie':
        return GradedCrossfire(cf, 'push', True)
    if atk == 'win' and tgt == 'loss':
        return GradedCrossfire(cf, 'hit', True)
    if atk == 'loss' and tgt == 'win':
        return GradedCrossfire(cf, 'miss', True)
    # Both won or both lost (shouldn't happen with opposite sides + no ties)
    return GradedCrossfire(cf, 'push', True)


def place_crossfire(attacker: User, target: User, game: Game) -> Crossfire:
    """Validate and create a crossfire. Raises CrossfireError on rule breach."""
    if attacker.id == target.id:
        raise CrossfireError("You can't crossfire yourself.")
    if game.has_started:
        raise CrossfireError("That game has already locked.")
    if game.season != settings.NFL_SEASON and game.season != getattr(settings, 'NFL_SEASON', game.season):
        pass  # allow historical seasons if explicitly targeted
    season, week = game.season, game.week

    if tokens_left(attacker, season, week) <= 0:
        raise CrossfireError(
            f"You're out of Crossfire tokens this week ({TOKENS_PER_WEEK} max)."
        )

    if Crossfire.objects.filter(attacker=attacker, game=game).exists():
        raise CrossfireError("You already have a Crossfire on this game.")

    try:
        atk_pick = Pick.objects.get(user=attacker, game=game)
        tgt_pick = Pick.objects.get(user=target, game=game)
    except Pick.DoesNotExist:
        raise CrossfireError(
            "Both of you need a pick on this game before you can fire."
        )

    if atk_pick.team_picked == tgt_pick.team_picked:
        raise CrossfireError(
            "Crossfire only works when you picked the opposite side."
        )

    with transaction.atomic():
        return Crossfire.objects.create(
            season=season,
            week=week,
            attacker=attacker,
            target=target,
            game=game,
            attacker_side=atk_pick.team_picked,
            target_side=tgt_pick.team_picked,
        )


def cancel_crossfire(attacker: User, crossfire_id: int) -> None:
    try:
        cf = Crossfire.objects.select_related('game').get(
            pk=crossfire_id, attacker=attacker
        )
    except Crossfire.DoesNotExist:
        raise CrossfireError("Crossfire not found.")
    if cf.game.has_started:
        raise CrossfireError("Too late — that game has locked.")
    cf.delete()


def week_board(season: int, week: int, viewer: Optional[User] = None) -> dict:
    """Everything the Crossfire page needs for one week."""
    cfs = list(
        Crossfire.objects.filter(season=season, week=week)
        .select_related('attacker', 'target', 'game')
        .order_by('-created_at')
    )
    games = {cf.game_id: cf.game for cf in cfs}
    graded = [grade_crossfire(cf, games.get(cf.game_id)) for cf in cfs]

    # Most hunted picks (by target+game)
    hunt_counts: dict[tuple, dict] = {}
    for g in graded:
        cf = g.crossfire
        key = (cf.target_id, cf.game_id)
        bucket = hunt_counts.setdefault(key, {
            'target': cf.target,
            'game': cf.game,
            'target_side': cf.target_side,
            'count': 0,
            'hits_against': 0,
            'pending': 0,
        })
        bucket['count'] += 1
        if g.result == 'hit':
            bucket['hits_against'] += 1
        elif g.result == 'pending':
            bucket['pending'] += 1
    most_wanted = sorted(
        hunt_counts.values(), key=lambda b: (-b['count'], b['target'].username)
    )[:MAX_HUNTED_BOARD]

    # Sharpshooter standings this week
    stats: dict[int, dict] = defaultdict(lambda: {
        'user': None, 'fired': 0, 'hits': 0, 'misses': 0, 'pending': 0,
    })
    for g in graded:
        s = stats[g.crossfire.attacker_id]
        s['user'] = g.crossfire.attacker
        s['fired'] += 1
        if g.result == 'hit':
            s['hits'] += 1
        elif g.result == 'miss':
            s['misses'] += 1
        elif g.result == 'pending':
            s['pending'] += 1
    sharpshooters = sorted(
        stats.values(),
        key=lambda s: (-s['hits'], s['misses'], -s['fired'], s['user'].username),
    )

    # Survival board: targets who absorbed the most fire and still won
    survived = [
        b for b in most_wanted
        if b['hits_against'] == 0 and b['pending'] == 0 and b['count'] >= 2
    ]

    my_fired = my_received = []
    tokens = None
    if viewer and viewer.is_authenticated:
        my_fired = [g for g in graded if g.crossfire.attacker_id == viewer.id]
        my_received = [g for g in graded if g.crossfire.target_id == viewer.id]
        tokens = {
            'left': tokens_left(viewer, season, week),
            'used': tokens_used(viewer, season, week),
            'max': TOKENS_PER_WEEK,
        }

    return {
        'season': season,
        'week': week,
        'graded': graded,
        'most_wanted': most_wanted,
        'sharpshooters': sharpshooters,
        'survived': survived,
        'my_fired': my_fired,
        'my_received': my_received,
        'tokens': tokens,
        'total_crossfires': len(cfs),
    }


def season_sharpshooters(season: int, limit: int = 15) -> list[dict]:
    cfs = Crossfire.objects.filter(season=season).select_related(
        'attacker', 'game'
    )
    stats: dict[int, dict] = defaultdict(lambda: {
        'user': None, 'fired': 0, 'hits': 0, 'misses': 0,
    })
    for cf in cfs:
        g = grade_crossfire(cf)
        s = stats[cf.attacker_id]
        s['user'] = cf.attacker
        s['fired'] += 1
        if g.result == 'hit':
            s['hits'] += 1
        elif g.result == 'miss':
            s['misses'] += 1
    rows = list(stats.values())
    for s in rows:
        decided = s['hits'] + s['misses']
        s['accuracy'] = (s['hits'] / decided) if decided else None
    rows.sort(key=lambda s: (-(s['hits']), s['misses'], s['user'].username))
    return rows[:limit]


def fire_targets_for_game(attacker: User, game: Game) -> list[dict]:
    """People the attacker could crossfire on this game (opposite pick, open)."""
    if game.has_started:
        return []
    try:
        my_side = Pick.objects.get(user=attacker, game=game).team_picked
    except Pick.DoesNotExist:
        return []

    already = set(
        Crossfire.objects.filter(attacker=attacker, game=game)
        .values_list('target_id', flat=True)
    )
    opposite = list(
        Pick.objects.filter(game=game)
        .exclude(user=attacker)
        .exclude(team_picked=my_side)
        .select_related('user')
    )
    friends = {u.id for u in friend_users(attacker)}
    rows = []
    for p in opposite:
        if p.user_id in already:
            continue
        rows.append({
            'user': p.user,
            'side': p.team_picked,
            'is_friend': p.user_id in friends,
        })
    rows.sort(key=lambda r: (not r['is_friend'], r['user'].username.lower()))
    return rows


def heat_on_picks(user: User, game_ids: Iterable[int]) -> dict[int, int]:
    """How many crossfires are aimed at this user's pick on each game."""
    rows = (
        Crossfire.objects.filter(target=user, game_id__in=list(game_ids))
        .values('game_id')
        .annotate(n=Count('id'))
    )
    return {r['game_id']: r['n'] for r in rows}
