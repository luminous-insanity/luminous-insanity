"""Shareable moment cards — perfect weeks, rivalry wins, hot streaks.

Plain server-rendered pages designed to look good when linked or screenshotted.
No external OG image service required.
"""
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.conf import settings

from api.models import Game
from api.rules import grade_pick
from .models import Pick, Challenge, AchievementUnlock
from .standings import standing_for
from .titles import display_title


def _week_record(user, season, week):
    picks = Pick.objects.filter(
        user=user, game__season=season, game__week=week,
        game__status=Game.FINAL,
        game__home_score__isnull=False,
        game__away_score__isnull=False,
    ).select_related('game')
    wins = losses = ties = 0
    total_games = Game.objects.filter(season=season, week=week).count()
    for pick in picks:
        outcome = grade_pick(pick.team_picked, pick.game.home_score, pick.game.away_score)
        if outcome == 'win':
            wins += 1
        elif outcome == 'loss':
            losses += 1
        elif outcome == 'tie':
            ties += 1
    perfect = (wins + losses + ties) == total_games and losses == 0 and ties == 0 and total_games > 0
    return {
        'wins': wins, 'losses': losses, 'ties': ties,
        'total_games': total_games, 'perfect': perfect,
        'picked': wins + losses + ties,
    }


def share_perfect_week(request, user_id, season, week):
    player = get_object_or_404(User, pk=user_id)
    record = _week_record(player, season, week)
    if not record['perfect']:
        # Still show the card, but mark as not perfect
        pass
    title = display_title(player)
    return render(request, 'accounts/share_moment.html', {
        'moment_kind': 'perfect_week',
        'player': player,
        'player_title': title,
        'season': season,
        'week': week,
        'record': record,
        'headline': f"Perfect Week {week}" if record['perfect'] else f"Week {week} report",
        'subline': f"{record['wins']}-{record['losses']}-{record['ties']} · {season} season",
        'share_url': request.build_absolute_uri(
            reverse('share_perfect_week', args=[player.id, season, week])
        ),
    })


def share_challenge(request, challenge_id):
    challenge = get_object_or_404(
        Challenge.objects.select_related('challenger', 'opponent'),
        pk=challenge_id,
    )
    # Only show completed-ish challenges publicly as a moment
    return render(request, 'accounts/share_moment.html', {
        'moment_kind': 'challenge',
        'challenge': challenge,
        'player': challenge.challenger,
        'opponent': challenge.opponent,
        'season': challenge.season,
        'week': challenge.week,
        'headline': f"{challenge.challenger.username} vs {challenge.opponent.username}",
        'subline': f"Week {challenge.week} · {challenge.season} · {challenge.get_status_display()}",
        'share_url': request.build_absolute_uri(
            reverse('share_challenge', args=[challenge.id])
        ),
    })


@login_required
def my_share_links(request):
    """List recent shareable moments for the signed-in user."""
    season = settings.NFL_SEASON
    # Find perfect weeks this season
    perfect_weeks = []
    for week in range(1, 19):
        record = _week_record(request.user, season, week)
        if record['perfect']:
            perfect_weeks.append({'week': week, 'record': record})

    recent_challenges = Challenge.objects.filter(
        _challenge_q(request.user)
    ).select_related('challenger', 'opponent').order_by('-created_at')[:10]

    return render(request, 'accounts/share_hub.html', {
        'perfect_weeks': perfect_weeks,
        'challenges': recent_challenges,
        'season': season,
    })


def _challenge_q(user):
    from django.db.models import Q
    return Q(challenger=user) | Q(opponent=user)
