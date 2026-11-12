"""Site analytics for staff: how people are using the game.

Built from data the site already has (sign-ups, picks, chat, leagues), so
nothing extra is tracked and no outside service is involved. Read-only.
Shown at /accounts/staff/analytics/ to staff members only.
"""
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Count
from django.utils import timezone

from api.models import Game

from .leaderboard import last_active_map
from .models import (
    ChatReport, ChatSanction, FriendRequest, League, LeagueMembership, LiveChatMessage,
    Pick, TiebreakerPick,
)


def _monday(dt):
    day = timezone.localtime(dt).date()
    return day - timedelta(days=day.weekday())


def _share(part, whole):
    return round(part / whole * 100, 1) if whole else None


def build_site_analytics(now=None, season=None, weeks_back=12):
    now = now or timezone.now()
    season = season or settings.NFL_SEASON
    players = User.objects.filter(is_superuser=False)
    total = players.count()

    # ---- who is around ---------------------------------------------------
    last_active = last_active_map()
    player_ids = set(players.values_list('id', flat=True))

    def active_within(days):
        cutoff = now - timedelta(days=days)
        return sum(1 for uid, when in last_active.items() if uid in player_ids and when >= cutoff)

    joined = list(players.values_list('date_joined', flat=True))
    new_7 = sum(1 for d in joined if d >= now - timedelta(days=7))
    new_30 = sum(1 for d in joined if d >= now - timedelta(days=30))

    # ---- sign-ups per week ----------------------------------------------
    this_monday = _monday(now)
    starts = [this_monday - timedelta(weeks=i) for i in range(weeks_back - 1, -1, -1)]
    signups = {start: 0 for start in starts}
    for d in joined:
        start = _monday(d)
        if start in signups:
            signups[start] += 1
    signup_rows = [{'week_of': s, 'count': c} for s, c in signups.items()]
    peak_signups = max([r['count'] for r in signup_rows] or [0]) or 1
    for row in signup_rows:
        row['bar'] = round(row['count'] / peak_signups * 100)

    # ---- the funnel: sign-up -> first pick -> coming back ------------------
    season_picks = Pick.objects.filter(game__season=season, user__is_superuser=False)
    per_user_weeks = {
        row['user_id']: row['weeks']
        for row in season_picks.values('user_id').annotate(weeks=Count('game__week', distinct=True))
    }
    ever_picked = set(Pick.objects.filter(user__is_superuser=False)
                      .values_list('user_id', flat=True).distinct())
    picked_season = len(per_user_weeks)
    three_weeks = sum(1 for w in per_user_weeks.values() if w >= 3)
    week_ago = now - timedelta(days=7)
    stalled = sum(
        1 for u in players.filter(date_joined__lt=week_ago).values_list('id', flat=True)
        if u not in ever_picked)
    funnel = [
        {'label': 'Signed up', 'count': total, 'share': 100.0 if total else None},
        {'label': f'Made a pick in {season}', 'count': picked_season, 'share': _share(picked_season, total)},
        {'label': 'Picked in 3+ different weeks', 'count': three_weeks, 'share': _share(three_weeks, total)},
    ]

    # ---- picks and players by week, and week-to-week retention -----------
    weekly = []
    pickers = {}
    for row in (season_picks.values('game__week')
                .annotate(picks=Count('id'), players=Count('user_id', distinct=True))
                .order_by('game__week')):
        weekly.append({'week': row['game__week'], 'picks': row['picks'], 'players': row['players']})
    for row in season_picks.values('game__week', 'user_id').distinct():
        pickers.setdefault(row['game__week'], set()).add(row['user_id'])
    peak_players = max([r['players'] for r in weekly] or [0]) or 1
    for row in weekly:
        row['bar'] = round(row['players'] / peak_players * 100)
        prev = pickers.get(row['week'] - 1)
        row['retained'] = (_share(len(prev & pickers[row['week']]), len(prev)) if prev else None)

    # ---- chat and safety ---------------------------------------------------
    chat_week = LiveChatMessage.objects.filter(
        created_at__gte=week_ago, kind__in=[LiveChatMessage.SAY, LiveChatMessage.EMOTE])
    chat = {
        'messages_7d': chat_week.count(),
        'chatters_7d': chat_week.values('author_id').distinct().count(),
        'open_reports': ChatReport.objects.filter(status=ChatReport.OPEN).count(),
        'hidden_7d': LiveChatMessage.objects.filter(created_at__gte=week_ago, is_hidden=True).count(),
        'active_timeouts': sum(1 for s in ChatSanction.objects.filter(revoked=False) if s.is_active),
    }

    # ---- social features ---------------------------------------------------
    leagues_count = League.objects.count()
    in_league = LeagueMembership.objects.values('user_id').distinct().count()
    friends_accepted = FriendRequest.objects.filter(status=FriendRequest.ACCEPTED).count()
    social = {
        'friendships': friends_accepted,
        'leagues': leagues_count,
        'players_in_a_league': in_league,
        'avg_league_size': (round(LeagueMembership.objects.count() / leagues_count, 1)
                            if leagues_count else None),
        'tiebreaker_guesses': TiebreakerPick.objects.filter(game__season=season).count(),
    }

    latest = Game.objects.filter(season=season, status=Game.FINAL).order_by('-week').values_list(
        'week', flat=True).first()
    return {
        'season': season,
        'generated_at': now,
        'totals': {
            'players': total,
            'active_7d': active_within(7),
            'active_30d': active_within(30),
            'new_7d': new_7,
            'new_30d': new_30,
            'never_picked_over_7d': stalled,
        },
        'signups': signup_rows,
        'funnel': funnel,
        'weekly': weekly,
        'chat': chat,
        'social': social,
        'latest_final_week': latest,
    }
