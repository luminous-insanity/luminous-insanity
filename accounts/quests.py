"""Weekly quest board — multiple side objectives that refresh each NFL week.

Quests never change W-L-T. They give players clear things to do before/during
a week and surface progress on the Command Center.
"""
from django.conf import settings
from django.db.models import Q

from api.models import Game
from api.rules import grade_pick
from api.services import current_week, get_team_records
from .models import Pick, Challenge, FriendRequest, Crossfire
from .live_features import underdog_hunter_quest


def _pct(rec):
    if not rec:
        return None
    w = rec.get('wins') or rec.get('W') or 0
    l = rec.get('losses') or rec.get('L') or 0
    t = rec.get('ties') or rec.get('T') or 0
    n = w + l + t
    return (w + 0.5 * t) / n if n else None


def build_weekly_quests(user, season=None, week=None):
    """Return a list of quest dicts for the dashboard quest board."""
    season = season or settings.NFL_SEASON
    week = week or current_week()
    games = list(Game.objects.filter(season=season, week=week))
    total = len(games)
    picks = {
        p.game_id: p
        for p in Pick.objects.filter(user=user, game__season=season, game__week=week)
    }
    picked = len(picks)
    locked_conf = sum(
        1 for p in picks.values()
        if p.confidence == Pick.CONFIDENCE_LOCK
    )
    solid_or_lock = sum(
        1 for p in picks.values()
        if p.confidence in (Pick.CONFIDENCE_SOLID, Pick.CONFIDENCE_LOCK)
    )

    # Underdog quest (reuse live_features)
    dog = underdog_hunter_quest(user, season, week)

    # Crossfire mission: use all three weekly shots against opposing picks.
    crossfire_fired = Crossfire.objects.filter(
        attacker=user, season=season, week=week
    ).count()

    # Challenge a friend this week
    has_challenge = Challenge.objects.filter(
        Q(challenger=user) | Q(opponent=user),
        season=season,
        week=week,
        status__in=(Challenge.PENDING, Challenge.ACCEPTED),
    ).exists()
    friend_count = FriendRequest.objects.filter(
        status=FriendRequest.ACCEPTED,
    ).filter(Q(sender=user) | Q(receiver=user)).count()

    # Correct picks so far this week (graded only)
    correct = 0
    graded = 0
    for p in picks.values():
        g = p.game if hasattr(p, 'game') and p.game_id else None
    # Need game scores — reload with select_related
    picks_list = list(
        Pick.objects.filter(
            user=user, game__season=season, game__week=week
        ).select_related('game')
    )
    for p in picks_list:
        if not p.game.is_final:
            continue
        graded += 1
        if grade_pick(p.team_picked, p.game.home_score, p.game.away_score) == 'win':
            correct += 1

    quests = [
        {
            'key': 'lock_slate',
            'icon': '📋',
            'title': 'Lock the slate',
            'detail': 'Make a pick for every game this week.',
            'current': picked,
            'target': total or 1,
            'complete': total > 0 and picked >= total,
            'cta': 'picks',
            'cta_label': 'Make picks',
        },
        {
            'key': 'underdog_hunter',
            'icon': '🐕',
            'title': 'Underdog Hunter',
            'detail': f"Back at least {dog['target'] or 1} underdog(s).",
            'current': dog['taken'],
            'target': dog['target'] or 1,
            'complete': dog['complete'],
            'cta': 'picks',
            'cta_label': 'Hunt dogs',
        },
        {
            'key': 'trust_your_gut',
            'icon': '🔐',
            'title': 'Trust your gut',
            'detail': 'Mark at least 3 picks as Solid or Lock.',
            'current': min(solid_or_lock, 3),
            'target': 3,
            'complete': solid_or_lock >= 3,
            'cta': 'picks',
            'cta_label': 'Set confidence',
        },
        {
            'key': 'crossfire_three_shots',
            'icon': '🎯',
            'title': 'Three-shot Crossfire',
            'detail': 'Fire all 3 Crossfire shots this week.',
            'current': min(crossfire_fired, 3),
            'target': 3,
            'complete': crossfire_fired >= 3,
            'cta': 'crossfire',
            'cta_label': 'Open Crossfire',
        },
        {
            'key': 'throw_the_flag',
            'icon': '⚔️',
            'title': 'Throw the flag',
            'detail': 'Challenge a friend for this week (or a game in it).',
            'current': 1 if has_challenge else 0,
            'target': 1,
            'complete': has_challenge,
            'cta': 'challenges',
            'cta_label': 'Challenges' if friend_count else 'Add friends first',
            'disabled': friend_count == 0 and not has_challenge,
        },
    ]

    # Bonus quest when some games are final
    if graded >= 3:
        quests.append({
            'key': 'hot_hand',
            'icon': '🔥',
            'title': 'Hot hand',
            'detail': 'Go at least 3 correct on graded games this week.',
            'current': min(correct, 3),
            'target': 3,
            'complete': correct >= 3,
            'cta': 'picks',
            'cta_label': 'See results',
        })

    done = sum(1 for q in quests if q['complete'])
    return {
        'week': week,
        'season': season,
        'quests': quests,
        'completed': done,
        'total': len(quests),
        'all_complete': done == len(quests) and len(quests) > 0,
    }
