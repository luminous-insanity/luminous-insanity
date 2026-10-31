"""Weekly recap — post-week summary of record, confidence, friends, and highlights."""
from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Q

from api.models import Game
from api.rules import grade_pick
from api.services import current_week
from .models import Pick, FriendRequest, Challenge, GameReaction
from .standings import compute_standings, standing_for
from .confidence import confidence_points_for_user
from .live_features import rivalry_timeline


def build_week_recap(user, season=None, week=None):
    season = season or settings.NFL_SEASON
    week = week if week is not None else current_week()

    games = list(
        Game.objects.filter(season=season, week=week).order_by('game_date', 'kickoff', 'id')
    )
    picks = {
        p.game_id: p
        for p in Pick.objects.filter(user=user, game__in=games).select_related('game')
    }

    wins = losses = ties = pending = 0
    highlights = []
    for game in games:
        pick = picks.get(game.pk)
        if not pick:
            if game.is_final:
                losses += 0  # no pick doesn't count as loss in recap graded-only
            continue
        if not game.is_final:
            pending += 1
            continue
        outcome = grade_pick(pick.team_picked, game.home_score, game.away_score)
        if outcome == 'win':
            wins += 1
            team = game.home_team if pick.team_picked == Pick.HOME else game.away_team
            if pick.confidence == Pick.CONFIDENCE_LOCK:
                highlights.append({
                    'kind': 'lock',
                    'text': f'Lock hit: {team}',
                    'icon': '🔐',
                })
            else:
                highlights.append({
                    'kind': 'win',
                    'text': f'Correct: {team}',
                    'icon': '✓',
                })
        elif outcome == 'loss':
            losses += 1
        elif outcome == 'tie':
            ties += 1

    # Keep highlights short
    highlights = highlights[:8]

    standing = standing_for(user, week=week, season=season)
    conf = confidence_points_for_user(user, season=season, week=week)

    # Friends comparison
    friend_ids = set()
    for fr in FriendRequest.objects.filter(status=FriendRequest.ACCEPTED).filter(
        Q(sender=user) | Q(receiver=user)
    ):
        other = fr.receiver_id if fr.sender_id == user.id else fr.sender_id
        friend_ids.add(other)
    friend_rows = []
    if friend_ids:
        friends = list(User.objects.filter(id__in=friend_ids))
        rows = compute_standings(
            week=week, season=season, users=[user] + friends, with_pending=True
        )
        friend_rows = [
            {
                'user': r.user,
                'wins': r.wins,
                'losses': r.losses,
                'ties': r.ties,
                'rank': r.rank,
                'is_me': r.user.id == user.id,
            }
            for r in rows[:8]
        ]

    # Challenges this week
    challenges = list(
        Challenge.objects.filter(
            Q(challenger=user) | Q(opponent=user),
            season=season,
            week=week,
        ).select_related('challenger', 'opponent')[:5]
    )

    reactions = GameReaction.objects.filter(
        user=user, game__season=season, game__week=week
    ).count()

    final_count = sum(1 for g in games if g.is_final)
    week_complete = len(games) > 0 and final_count == len(games)

    return {
        'season': season,
        'week': week,
        'wins': wins,
        'losses': losses,
        'ties': ties,
        'pending': pending,
        'record': f'{wins}-{losses}-{ties}',
        'standing': standing,
        'confidence_points': conf['points'],
        'underdog_locks': conf['underdog_locks'],
        'highlights': highlights,
        'friend_rows': friend_rows,
        'challenges': challenges,
        'reactions': reactions,
        'games_total': len(games),
        'games_final': final_count,
        'week_complete': week_complete,
        'picked_count': len(picks),
    }
