"""Live energy, underdog hunter side-quest, and confidence board.

All derived from existing picks, games, and reactions — no parallel scoring system.
"""
import logging
from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.utils import timezone

from api.models import Game
from api.rules import grade_pick
from api.services import get_team_records, current_week
from .models import Pick, GameReaction
from .confidence import is_underdog_pick, confidence_points_for_user

log = logging.getLogger(__name__)


def _pct(rec):
    if not rec:
        return None

    w = int(rec.get('wins') or rec.get('W') or 0)
    l = int(rec.get('losses') or rec.get('L') or 0)
    t = int(rec.get('ties') or rec.get('T') or 0)

    n = w + l + t
    return (w + 0.5 * t) / n if n else None


def underdog_hunter_quest(user, season=None, week=None, team_records=None):
    """Weekly side-quest: pick underdogs and optionally lock them.

    Returns progress dict for dashboard/picks. Does not change W-L-T.
    """
    season = season or settings.NFL_SEASON
    week = week or current_week()
    if team_records is None:
        try:
            team_records = get_team_records()
        except Exception:
            team_records = {}

    games = list(Game.objects.filter(season=season, week=week).order_by('game_date', 'kickoff'))
    underdog_games = []
    for game in games:
        home_pct = _pct(team_records.get(game.home_team))
        away_pct = _pct(team_records.get(game.away_team))
        if home_pct is None or away_pct is None:
            continue
        if home_pct < away_pct:
            underdog_games.append((game, 'home', game.home_team))
        elif away_pct < home_pct:
            underdog_games.append((game, 'away', game.away_team))

    picks = {
        p.game_id: p
        for p in Pick.objects.filter(user=user, game__season=season, game__week=week)
    }

    taken = 0
    locked = 0
    correct = 0
    correct_locks = 0
    for game, side, name in underdog_games:
        pick = picks.get(game.pk)
        if not pick or pick.team_picked != side:
            continue
        taken += 1
        if pick.confidence == Pick.CONFIDENCE_LOCK:
            locked += 1
        if game.is_final:
            outcome = grade_pick(pick.team_picked, game.home_score, game.away_score)
            if outcome == 'win':
                correct += 1
                if pick.confidence == Pick.CONFIDENCE_LOCK:
                    correct_locks += 1

    target = min(3, len(underdog_games)) if underdog_games else 0
    return {
        'week': week,
        'season': season,
        'underdog_count': len(underdog_games),
        'target': target,
        'taken': taken,
        'locked': locked,
        'correct': correct,
        'correct_locks': correct_locks,
        'complete': target > 0 and taken >= target,
        'underdog_games': [
            {'game': g, 'side': s, 'team': t, 'picked': picks.get(g.pk) and picks[g.pk].team_picked == s}
            for g, s, t in underdog_games[:8]
        ],
    }


def live_game_moments(season=None, week=None, limit=12):
    """Recent reactions on live or just-finished games for the energy feed."""
    season = season or settings.NFL_SEASON
    week = week or current_week()
    now = timezone.now()

    games = Game.objects.filter(season=season, week=week).filter(
        Q(status=Game.LIVE) |
        Q(status=Game.FINAL) |
        Q(kickoff__lte=now, kickoff__gte=now - timedelta(hours=8))
    )
    # Fallback: any game this week that has started
    if not games.exists():
        games = Game.objects.filter(season=season, week=week)

    reactions = (
        GameReaction.objects.filter(game__in=games)
        .select_related('user', 'game')
        .order_by('-created_at')[:limit]
    )
    live_games = []
    for g in Game.objects.filter(season=season, week=week).order_by('kickoff', 'id'):
        if g.has_started and not g.is_final:
            live_games.append(g)
        elif g.is_final and g.kickoff and (now - g.kickoff).total_seconds() < 6 * 3600:
            live_games.append(g)

    return {
        'reactions': list(reactions),
        'live_games': live_games[:10],
        'week': week,
        'season': season,
    }


def confidence_board(season=None, week=None, users=None, limit=25):
    """Rank players by confidence points (season or week)."""
    season = season or settings.NFL_SEASON
    try:
        team_records = get_team_records()
    except Exception:
        team_records = {}

    if users is None:
        user_ids = Pick.objects.filter(
            game__season=season,
            confidence__isnull=False,
        ).values_list('user_id', flat=True).distinct()
        users = list(User.objects.filter(id__in=user_ids, is_superuser=False))
    else:
        users = list(users)

    rows = []
    for user in users:
        try:
            stats = confidence_points_for_user(user, season=season, week=week, team_records=team_records)
            if stats.get('points') or stats.get('underdog_locks'):
                rows.append({
                    'user': user,
                    'points': stats.get('points', 0),
                    'underdog_locks': stats.get('underdog_locks', 0),
                })
        except Exception:
            # One bad user/pick must not take down the whole confidence leaderboard
            log.exception("Confidence calc failed for user %s", getattr(user, 'pk', None))
            continue
    rows.sort(key=lambda r: (-r['points'], -r['underdog_locks'], (r['user'].username or '').lower()))
    for i, row in enumerate(rows[:limit], start=1):
        row['rank'] = i
    return rows[:limit]


def rivalry_timeline(user_a, user_b, season=None, limit=12):
    """Head-to-head week results between two players for a season."""
    season = season or settings.NFL_SEASON
    from .standings import compute_standings

    weeks = sorted(
        set(
            Pick.objects.filter(
                user__in=[user_a, user_b],
                game__season=season,
                game__status=Game.FINAL,
            ).values_list('game__week', flat=True)
        )
    )
    timeline = []
    a_wins = b_wins = ties = 0
    for week in weeks:
        standings = compute_standings(
            week=week, season=season, users=[user_a, user_b], with_pending=False
        )
        by_id = {s.user_id: s for s in standings}
        sa, sb = by_id.get(user_a.id), by_id.get(user_b.id)
        if not sa or not sb:
            continue
        if sa.completed == 0 and sb.completed == 0:
            continue
        # Compare weekly records
        if (sa.wins, -sa.losses) > (sb.wins, -sb.losses):
            winner = user_a
            a_wins += 1
            result = 'a'
        elif (sb.wins, -sb.losses) > (sa.wins, -sa.losses):
            winner = user_b
            b_wins += 1
            result = 'b'
        else:
            winner = None
            ties += 1
            result = 'tie'
        timeline.append({
            'week': week,
            'a_record': f'{sa.wins}-{sa.losses}-{sa.ties}',
            'b_record': f'{sb.wins}-{sb.losses}-{sb.ties}',
            'winner': winner,
            'result': result,
        })
        if len(timeline) >= limit:
            break

    return {
        'timeline': timeline,
        'a_wins': a_wins,
        'b_wins': b_wins,
        'ties': ties,
        'season': season,
    }


def social_drawer_context(request):
    """Data for the site-wide Social drawer (same on every page).

    Safe to call from a context processor. Returns {} for anonymous users.
    """
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {}

    from django.conf import settings
    from django.contrib.auth.models import User
    from django.db.models import Count, Q
    from django.urls import reverse

    from accounts.models import FriendRequest, PerformanceReaction, Challenge
    from accounts.playermenu import menu_data
    from accounts.leaderboard import default_week
    from accounts.standings import standing_for
    from api.services import current_week

    selected_season = getattr(settings, 'NFL_SEASON', 2026)
    try:
        q_season = request.GET.get('season')
        if q_season:
            selected_season = int(q_season)
    except (TypeError, ValueError):
        pass

    mission_week = (
        current_week() if selected_season == getattr(settings, 'NFL_SEASON', selected_season)
        else default_week(selected_season)
    )
    reaction_week = default_week(selected_season)

    friend_query = (request.GET.get('friend_search') or '').strip()
    friend_results = User.objects.none()
    if friend_query:
        friend_results = User.objects.filter(
            username__icontains=friend_query
        ).exclude(pk=user.pk).order_by('username')[:20]

    incoming_requests = FriendRequest.objects.filter(
        receiver=user,
        status=FriendRequest.PENDING,
    ).select_related('sender').order_by('-created_at')

    accepted_requests = FriendRequest.objects.filter(
        status=FriendRequest.ACCEPTED,
    ).filter(
        Q(sender=user) | Q(receiver=user)
    ).select_related('sender', 'receiver')

    friends = [
        fr.receiver if fr.sender_id == user.id else fr.sender
        for fr in accepted_requests
    ]

    menus = menu_data(
        friends, user, selected_season,
        compare_week=reaction_week,
    )
    friend_rows = []
    for f in friends:
        row = {'user': f, 'menu': menus.get(f.id) or {}}
        row['reaction_url'] = reverse('react_to_performance', args=[f.id])
        counts = {
            item['emoji']: item['total']
            for item in PerformanceReaction.objects.filter(
                player=f, season=selected_season, week=reaction_week
            ).values('emoji').annotate(total=Count('id'))
        }
        row['reaction_counts'] = counts
        row['my_reaction'] = PerformanceReaction.objects.filter(
            reactor=user, player=f, season=selected_season, week=reaction_week
        ).first()
        row['reaction_clap'] = counts.get('👏', 0)
        row['reaction_fire'] = counts.get('🔥', 0)
        row['reaction_crown'] = counts.get('👑', 0)
        friend_rows.append(row)

    site_url = getattr(settings, 'SITE_URL', '').rstrip('/')
    signup_path = reverse('signup')
    invite_url = (
        f'{site_url}{signup_path}' if site_url
        else request.build_absolute_uri(signup_path)
    )
    invite_text = (
        f"{user.username} invited you to GameDayPicks! "
        "Pick NFL winners every week and see who does best among friends. "
        "Join here:"
    )

    shared_moment_weeks = []
    for share_week in range(1, 19):
        try:
            share_record = standing_for(user, week=share_week, season=selected_season)
        except Exception:
            continue
        if share_record and getattr(share_record, 'wins', 0) and getattr(share_record, 'losses', 1) == 0 and getattr(share_record, 'ties', 0) == 0 and share_record.wins > 0:
            shared_moment_weeks.append({'week': share_week, 'record': share_record})

    shared_moment_challenges = Challenge.objects.filter(
        Q(challenger=user) | Q(opponent=user),
        status=Challenge.ACCEPTED,
    ).select_related('challenger', 'opponent').order_by('-id')[:8]

    return {
        'social_selected_season': selected_season,
        'social_mission_week': mission_week,
        'social_reaction_week': reaction_week,
        'social_record_week': request.GET.get('record_week', 'season'),
        'friend_query': friend_query,
        'friend_results': friend_results,
        'incoming_requests': incoming_requests,
        'friend_rows': friend_rows,
        'invite_url': invite_url,
        'invite_text': invite_text,
        'invite_message': f'{invite_text} {invite_url}',
        'live_moments': live_game_moments(selected_season, mission_week),
        'shared_moment_weeks': shared_moment_weeks,
        'shared_moment_challenges': shared_moment_challenges,
    }
