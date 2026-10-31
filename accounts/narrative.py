"""Season narrative arcs — short, motivating stories from real standings data.

These never invent results. Every line is derived from graded picks,
streaks, and challenge state. Playoff status is shown in the dashboard
Path to Playoffs card.
"""
from django.conf import settings
from django.db.models import Q

from api.models import Game
from api.rules import grade_pick
from .models import Pick, Challenge
from .standings import standing_for


def _current_streak(user, season):
    """Count consecutive correct picks at the end of the graded sequence."""
    picks = (
        Pick.objects.filter(
            user=user,
            game__season=season,
            game__status=Game.FINAL,
            game__home_score__isnull=False,
            game__away_score__isnull=False,
        )
        .select_related('game')
        .order_by('-game__game_date', '-game__kickoff', '-game_id')
    )
    streak = 0
    for pick in picks:
        outcome = grade_pick(pick.team_picked, pick.game.home_score, pick.game.away_score)
        if outcome == 'win':
            streak += 1
        else:
            break
    return streak


def build_narratives(user, season=None):
    """Return a short list of narrative dicts for the dashboard."""
    season = season or settings.NFL_SEASON
    stories = []

    streak = _current_streak(user, season)
    if streak >= 5:
        stories.append({
            'kind': 'streak',
            'icon': '🔥',
            'headline': f'{streak}-pick hot streak',
            'detail': 'Keep it alive — every correct pick extends the fire.',
            'emphasis': 'hot',
        })
    elif streak >= 3:
        stories.append({
            'kind': 'streak',
            'icon': '⚡',
            'headline': f'{streak} correct in a row',
            'detail': 'A hot streak is forming. One more lock keeps the momentum.',
            'emphasis': 'warm',
        })


    standing = standing_for(user, season=season)
    if standing and standing.completed >= 5:
        if standing.win_pct is not None and standing.win_pct >= 0.7:
            stories.append({
                'kind': 'form',
                'icon': '👑',
                'headline': 'Elite form this season',
                'detail': f"{standing.wins}–{standing.losses}–{standing.ties} — you're playing like a contender.",
                'emphasis': 'gold',
            })
        elif standing.losses > standing.wins and standing.completed >= 8:
            stories.append({
                'kind': 'comeback',
                'icon': '💪',
                'headline': 'Comeback season still open',
                'detail': 'A strong stretch of weeks can flip the narrative. Start with this week.',
                'emphasis': 'comeback',
            })

    accepted = Challenge.objects.filter(
        status=Challenge.ACCEPTED,
    ).filter(Q(challenger=user) | Q(opponent=user)).count()
    if accepted:
        stories.append({
            'kind': 'rivalry',
            'icon': '⚔️',
            'headline': f"{accepted} active rivalr{'ies' if accepted != 1 else 'y'}",
            'detail': 'Head-to-head battles are live. Check Challenges for the scoreboard.',
            'emphasis': 'rivalry',
        })

    return stories[:4]
