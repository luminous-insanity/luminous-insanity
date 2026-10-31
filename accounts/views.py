# accounts/views.py

from django.db.models import Q, Count
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.utils import timezone
from datetime import timedelta
from api.models import Game
from api.services import MAX_WEEK, current_week, get_team_records
from .forms import LoginForm, SignUpForm
from .models import Pick, FriendRequest, PerformanceReaction, Challenge, AchievementUnlock
from . import challenges
from .leaderboard import default_week
from .playermenu import menu_data, stats_summary
from .standings import compute_standings, standing_for
from .achievements import achievement_summary
from .narrative import build_narratives
from .confidence import confidence_points_for_user
from .titles import display_title, available_titles
from .live_features import underdog_hunter_quest, live_game_moments, confidence_board
from .quests import build_weekly_quests
from .path_to_playoffs import path_to_playoffs
from .recap import build_week_recap
import logging


def signup_view(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')  # Log in the user after successful registration
            messages.success(request, 'Registration successful. Welcome!')
            return redirect('dashboard')
    else:
        form = SignUpForm()
    return render(request, 'accounts/signup.html', {'form': form})


def login_view(request):
    if request.method == 'POST':
        form = LoginForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, 'You have successfully logged in.')
            return redirect('dashboard')
    else:
        form = LoginForm()
    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    logout(request)
    messages.success(request, 'You have been logged out.')
    return redirect('login')


def _team_name(game, side):
    """'home' -> the home team's abbreviation, 'away' -> the away team's, else None."""
    if side == Pick.HOME:
        return game.home_team
    if side == Pick.AWAY:
        return game.away_team
    return None


def _selected_week(request, default):
    """Lets you browse other weeks with /accounts/dashboard/?week=3"""
    try:
        week = int(request.GET.get('week', ''))
    except ValueError:
        return default
    return week if 1 <= week <= MAX_WEEK else default


def _available_seasons():
    seasons = list(
        Game.objects.order_by()
        .values_list('season', flat=True)
        .distinct()
    )

    if settings.NFL_SEASON not in seasons:
        seasons.append(settings.NFL_SEASON)

    return sorted(seasons, reverse=True)


def _selected_season(request):
    seasons = _available_seasons()

    # Explicit season selections always win. Otherwise use the configured
    # season while it is still underway; once finalized, default to the latest
    # fully completed season rather than an empty/new offseason season.
    requested = request.GET.get('season')
    if requested is not None:
        try:
            season = int(requested)
        except (TypeError, ValueError):
            season = settings.NFL_SEASON
        if season not in seasons:
            season = settings.NFL_SEASON
        return season, seasons

    from .leaderboard import season_is_finalized
    configured_season = settings.NFL_SEASON
    configured_has_games = Game.objects.filter(season=configured_season).exists()
    if configured_has_games and not season_is_finalized(configured_season):
        return configured_season, seasons

    completed = [year for year in seasons if season_is_finalized(year)]
    return (max(completed) if completed else configured_season), seasons



@login_required
def dashboard(request):
    selected_season, seasons = _selected_season(request)

    record_week = request.GET.get('record_week', 'season')

    if record_week != 'season':
        try:
            record_week = int(record_week)
            if not 1 <= record_week <= MAX_WEEK:
                record_week = 'season'
        except (TypeError, ValueError):
            record_week = 'season'

    if record_week == 'season':
        user_stats = standing_for(request.user, season=selected_season)
    else:
        user_stats = standing_for(
            request.user,
            week=record_week,
            season=selected_season,
        )

    friend_query = request.GET.get('friend_search', '').strip()
    friend_results = User.objects.none()

    if friend_query:
        friend_results = User.objects.filter(
            username__icontains=friend_query
        ).exclude(
            pk=request.user.pk
        ).order_by('username')[:20]

    incoming_requests = FriendRequest.objects.filter(
        receiver=request.user,
        status=FriendRequest.PENDING,
    ).select_related('sender').order_by('-created_at')

    alert_friend_requests = FriendRequest.objects.filter(
        receiver=request.user,
        status=FriendRequest.PENDING,
        receiver_seen=False,
    ).select_related('sender').order_by('-created_at')
    unread_reactions = PerformanceReaction.objects.filter(
        player=request.user,
        is_read=False,
    )

    accepted_requests = FriendRequest.objects.filter(
        status=FriendRequest.ACCEPTED,
    ).filter(
        Q(sender=request.user) | Q(receiver=request.user)
    ).select_related('sender', 'receiver')

    friends = [
        friend_request.receiver
        if friend_request.sender_id == request.user.id
        else friend_request.sender
        for friend_request in accepted_requests
    ]

    # Weekly mission: an optional, low-pressure objective that gives players
    # something concrete to complete before kickoff without changing standings.
    mission_week = (
        current_week() if selected_season == settings.NFL_SEASON
        else default_week(selected_season)
    )

    # Weekly friend race: put the user's current week in a small, live-feeling
    # competition panel. This is a view over the existing pick/score data only;
    # it adds no stored totals and cannot affect the canonical leaderboard.
    weekly_race_rows = []
    weekly_race_my_row = None
    weekly_race_has_friends = bool(friends)
    if weekly_race_has_friends:
        race_users = [request.user] + friends
        weekly_race_rows = compute_standings(
            week=mission_week,
            season=selected_season,
            users=race_users,
            with_pending=True,
        )
        weekly_race_my_row = next(
            (row for row in weekly_race_rows if row.user.id == request.user.id),
            None,
        )
        # Keep the panel compact, but never hide the signed-in player if they
        # are outside the top five.
        top_race_rows = weekly_race_rows[:5]
        if weekly_race_my_row and all(
            row.user.id != request.user.id for row in top_race_rows
        ):
            top_race_rows.append(weekly_race_my_row)
        weekly_race_rows = top_race_rows

    mission_games = Game.objects.filter(season=selected_season, week=mission_week)
    mission_game_count = mission_games.count()
    mission_picked_count = Pick.objects.filter(
        user=request.user, game__season=selected_season, game__week=mission_week
    ).count()
    mission_percent = (
        round(mission_picked_count * 100 / mission_game_count)
        if mission_game_count else 0
    )
    mission_complete = bool(mission_game_count and mission_picked_count >= mission_game_count)

    # Expanded stats, the Challenges card, and the friend-tap menu.
    my_stats = stats_summary(request.user, selected_season)
    menus = menu_data(
        friends, request.user, selected_season,
        compare_week=default_week(selected_season),
    )
    friend_rows = [{'user': f, 'menu': menus[f.id]} for f in friends]
    for row in friend_rows:
        row['reaction_url'] = reverse('react_to_performance', args=[row['user'].id])
        row['reaction_counts'] = {
            item['emoji']: item['total'] for item in PerformanceReaction.objects.filter(
                player=row['user'], season=selected_season, week=default_week(selected_season)
            ).values('emoji').annotate(total=Count('id'))
        }
        row['my_reaction'] = PerformanceReaction.objects.filter(
            reactor=request.user, player=row['user'], season=selected_season,
            week=default_week(selected_season)
        ).first()
        row['reaction_clap'] = row['reaction_counts'].get('👏', 0)
        row['reaction_fire'] = row['reaction_counts'].get('🔥', 0)
        row['reaction_crown'] = row['reaction_counts'].get('👑', 0)

    # "Invite a Friend": a link to the sign-up page plus a ready-to-send message,
    # for people who aren't on GameDayPicks yet.
    site_url = getattr(settings, 'SITE_URL', '').rstrip('/')
    signup_path = reverse('signup')
    invite_url = (
        f'{site_url}{signup_path}' if site_url
        else request.build_absolute_uri(signup_path)
    )
    invite_text = (
        f"{request.user.username} invited you to GameDayPicks! "
        "Pick NFL winners every week and see who does best among friends. "
        "Join here:"
    )

    # A compact, informational feed. Keep it separate from notifications:
    # notifications are actions for the current user; this feed is recent competition activity.
    activity_feed = []
    friend_ids = [friend.id for friend in friends]
    if friend_ids:
        for unlock in AchievementUnlock.objects.filter(
            user_id__in=friend_ids
        ).select_related('user').order_by('-unlocked_at')[:8]:
            activity_feed.append({
                'at': unlock.unlocked_at,
                'kind': 'achievement',
                'icon': '🏆',
                'message': f'{unlock.user.username} earned an achievement.',
                'detail': f'Level {unlock.level}',
                'url': reverse('achievements'),
            })

    recent_challenges = Challenge.objects.filter(
        Q(challenger=request.user) | Q(opponent=request.user)
    ).select_related('challenger', 'opponent').order_by('-created_at')[:8]
    for challenge in recent_challenges:
        other_player = challenge.opponent if challenge.challenger_id == request.user.id else challenge.challenger
        if challenge.status == Challenge.PENDING:
            message = f'{challenge.challenger.username} challenged {challenge.opponent.username}.'
            icon = '⚔️'
        elif challenge.status == Challenge.ACCEPTED:
            message = f'{challenge.challenger.username} and {challenge.opponent.username} are competing.'
            icon = '🏈'
        elif challenge.status in (Challenge.DECLINED, Challenge.CANCELLED):
            message = f'The challenge between {challenge.challenger.username} and {challenge.opponent.username} was {challenge.get_status_display().lower()}.'
            icon = 'ℹ️'
        else:
            continue
        activity_feed.append({
            'at': challenge.responded_at or challenge.created_at,
            'kind': 'challenge',
            'icon': icon,
            'message': message,
            'detail': f'Season {challenge.season}, Week {challenge.week}',
            'url': reverse('challenges'),
        })

    activity_feed.sort(key=lambda item: item['at'], reverse=True)
    activity_feed = activity_feed[:10]

    context = {
        'mission_week': mission_week,
        'mission_game_count': mission_game_count,
        'mission_picked_count': mission_picked_count,
        'mission_percent': mission_percent,
        'mission_complete': mission_complete,
        'weekly_race_rows': weekly_race_rows,
        'weekly_race_my_row': weekly_race_my_row,
        'weekly_race_has_friends': weekly_race_has_friends,
        'weekly_race_url': (
            f"{reverse('leaderboard')}?tab=weekly&season={selected_season}"
            f"&week={mission_week}&filter=friends"
        ),
        'activity_feed': activity_feed,
        'invite_url': invite_url,
        'invite_text': invite_text,
        'invite_message': f'{invite_text} {invite_url}',
        'user_stats': user_stats,
        'record_week': record_week,
        'weeks': range(1, MAX_WEEK + 1),
        'selected_season': selected_season,
        'seasons': seasons,
        'friend_query': friend_query,
        'friend_results': friend_results,
        'incoming_requests': incoming_requests,
        'alert_friend_requests': alert_friend_requests,
        'notification_count': alert_friend_requests.count() + unread_reactions.count(),
        'friends': friends,
        'friend_rows': friend_rows,
        'reaction_choices': PerformanceReaction.choices,
        'reaction_week': default_week(selected_season),
        'received_reactions': unread_reactions.select_related('reactor').order_by('-created_at')[:15],
        'my_stats': my_stats,
        'pending_challenges': challenges.incoming_pending(request.user),
        'achievement_summary': achievement_summary(request.user),
        'narratives': build_narratives(request.user, selected_season),
        'player_title': display_title(request.user),
        'confidence_stats': confidence_points_for_user(request.user, season=selected_season),
        'underdog_quest': underdog_hunter_quest(request.user, selected_season, mission_week),
        'live_moments': live_game_moments(selected_season, mission_week),
        'confidence_board_preview': confidence_board(selected_season, users=([request.user] + friends) if friends else [request.user], limit=8),
        'weekly_quests': build_weekly_quests(request.user, selected_season, mission_week),
        'path_playoffs': path_to_playoffs(request.user, selected_season),
    }

    return render(request, 'accounts/dashboard.html', context)


@login_required
@require_POST
def mark_alerts_read(request):
    """Mark dashboard alerts as seen without changing pending requests."""
    PerformanceReaction.objects.filter(player=request.user, is_read=False).update(is_read=True)
    FriendRequest.objects.filter(
        receiver=request.user,
        status=FriendRequest.PENDING,
        receiver_seen=False,
    ).update(receiver_seen=True)
    return JsonResponse({'ok': True})


@login_required
def achievements_page(request):
    summary = achievement_summary(request.user)
    return render(request, 'accounts/achievements.html', summary)


@login_required
def picks(request, week_number=None):
    current = current_week()
    selected_season, seasons = _selected_season(request)
    try:
        team_records = get_team_records()
    except Exception:
        # Records are cosmetic. Never let an API problem break the picks page.
        logging.getLogger(__name__).exception("Could not load team records")
        team_records = {}
    selected_week = week_number or _selected_week(request, current)

    games = (
        Game.objects
        .filter(season=selected_season, week=selected_week)
        .order_by('game_date', 'kickoff', 'id')
    )

    user_picks = {
        p.game_id: p
        for p in Pick.objects.filter(
            user=request.user,
            game__in=games,
            game__season=selected_season,
        )
    }
    picks_by_game = {gid: p.team_picked for gid, p in user_picks.items()}

    # Aggregate every site's picks for each game. These percentages are based
    # only on users who have actually submitted a pick for that game.
    community_pick_counts = {}

    # Friend Pulse is deliberately hidden until kickoff. Before a game starts,
    # the normal friend-pick privacy rules apply; after kickoff, players can
    # see whether their call agrees with or goes against their accepted friends.
    friend_ids = set()
    if request.user.is_authenticated:
        accepted_friendships = FriendRequest.objects.filter(
            status=FriendRequest.ACCEPTED,
        ).filter(Q(sender=request.user) | Q(receiver=request.user))
        friend_ids = set(accepted_friendships.exclude(
            sender=request.user, receiver=request.user
        ).values_list('sender_id', flat=True)) | set(accepted_friendships.values_list('receiver_id', flat=True))
        friend_ids.discard(request.user.id)

    friend_pick_counts = {}
    if friend_ids:
        for row in Pick.objects.filter(
            game__in=games, user_id__in=friend_ids
        ).values('game_id', 'team_picked').annotate(total=Count('id')):
            friend_pick_counts.setdefault(row['game_id'], {'home': 0, 'away': 0})[
                row['team_picked']
            ] = row['total']
    for row in (
        Pick.objects.filter(game__in=games)
        .values('game_id', 'team_picked')
        .annotate(total=Count('id'))
    ):
        community_pick_counts.setdefault(row['game_id'], {'home': 0, 'away': 0})[
            row['team_picked']
        ] = row['total']

    game_data = []
    for game in games:
        # Show live scores as soon as the API has them; only grade/standings
        # still require is_final. Previously this gated on is_final only, so
        # mid-game scores never rendered even though sync_scores wrote them.
        has_scores = game.home_score is not None and game.away_score is not None
        counts = community_pick_counts.get(game.pk, {'home': 0, 'away': 0})
        community_total = counts['home'] + counts['away']
        away_percent = round(counts['away'] * 100 / community_total) if community_total else 0
        home_percent = 100 - away_percent if community_total else 0
        user_pick = picks_by_game.get(game.pk)
        friend_counts = friend_pick_counts.get(game.pk, {'home': 0, 'away': 0})
        friend_total = friend_counts['home'] + friend_counts['away']
        friend_same = friend_counts.get(user_pick, 0) if user_pick else 0
        friend_opposite = friend_total - friend_same if user_pick else 0
        friend_pulse = None
        if game.has_started and user_pick and friend_total:
            if friend_same > friend_opposite:
                friend_pulse = {
                    'kind': 'majority',
                    'headline': 'You backed the friend-group favorite',
                    'detail': f'{friend_same} friend{"s" if friend_same != 1 else ""} picked the same team as you.',
                }
            elif friend_same < friend_opposite:
                friend_pulse = {
                    'kind': 'contrarian',
                    'headline': 'You went against the group',
                    'detail': f'{friend_opposite} friend{"s" if friend_opposite != 1 else ""} picked the other team.',
                }
            else:
                friend_pulse = {
                    'kind': 'split',
                    'headline': 'Your friend group is split',
                    'detail': f'{friend_same} friend{"s" if friend_same != 1 else ""} agreed with you; {friend_opposite} picked the other team.',
                }
        # Underdog detection from team records (cosmetic + confidence bonus signal)
        home_rec = team_records.get(game.home_team) or {}
        away_rec = team_records.get(game.away_team) or {}

        def _pct(rec):
            w = int(rec.get('wins') or rec.get('W') or 0)
            l = int(rec.get('losses') or rec.get('L') or 0)
            t = int(rec.get('ties') or rec.get('T') or 0)
            n = w + l + t
            return (w + 0.5 * t) / n if n else None

        home_pct, away_pct = _pct(home_rec), _pct(away_rec)
        home_is_dog = away_is_dog = False
        if home_pct is not None and away_pct is not None:
            home_is_dog = home_pct < away_pct
            away_is_dog = away_pct < home_pct

        user_pick_obj = user_picks.get(game.game_id)
        game_data.append({
            'game': game,
            'kickoff_label': get_kickoff_label(game),
            'score': game if has_scores else None,
            'winner': game.winner_name or 'N/A',
            'pick_status': user_pick or 'Not Picked',
            'pick_team': _team_name(game, user_pick),
            'pick_available': not game.has_started,
            'hours_to_lock': (                round((game.lock_at - timezone.now()).total_seconds() / 3600, 1)                if (not game.has_started and game.lock_at)                else None            ),
            'pick_confidence': user_pick_obj.confidence if user_pick_obj else None,
            'home_record': home_rec or None,
            'away_record': away_rec or None,
            'home_is_underdog': home_is_dog,
            'away_is_underdog': away_is_dog,
            'community_pick_total': community_total,
            'community_away_percent': away_percent,
            'community_home_percent': home_percent,
            'show_community_picks': bool(user_pick and community_total),
            'friend_pulse': friend_pulse,
        })

    picked_count = sum(1 for item in game_data if item['pick_status'] in (Pick.HOME, Pick.AWAY))
    total_games = len(game_data)
    context = {
        'current_week': current,
        'selected_week': selected_week,
        'game_data': game_data,
        'selected_season': selected_season,
        'seasons': seasons,
        'picked_count': picked_count,
        'remaining_count': total_games - picked_count,
        'total_games': total_games,
        'pick_progress_percent': round((picked_count / total_games) * 100) if total_games else 0,
    }

    return render(request, 'accounts/picks.html', context)


def get_kickoff_label(game):
    now = timezone.localtime()

    # Normalize the API status
    status = (game.status or "").strip().lower().replace("-", "_").replace(" ", "_")

    # Completed games
    if status in {
        "final", "completed", "complete", "finished",
        "game_over", "closed"
    } or "final" in status:
        return "FINAL"

    # Games currently being played
    if status in {
        "in_progress", "inprogress", "live", "in_play",
        "inprogress_period"
    } or "in_progress" in status:
        return "IN PROGRESS"

    # No kickoff time available
    if not game.kickoff:
        return "TIME TBD"

    kickoff = timezone.localtime(game.kickoff)
    time_label = kickoff.strftime("%I:%M %p").lstrip("0")

    # Future games
    if kickoff > now:
        if kickoff.date() == now.date():
            return f"TODAY · {time_label}"

        if kickoff.date() == now.date() + timedelta(days=1):
            return f"TOMORROW · {time_label}"

        date_label = f"{kickoff.strftime('%a, %b')} {kickoff.day}"   # "Nov 5", not "Nov 05"
        return f"{date_label} · {time_label}"

    # Kickoff has passed, but the API has not reported a final status
    return "IN PROGRESS"

@login_required
@require_POST
def make_pick(request, game_id):
    game = get_object_or_404(Game, game_id=game_id)
    back = f"{reverse('picks')}?season={game.season}&week={game.week}"

    team_picked = request.POST.get('team_picked')
    if team_picked not in (Pick.HOME, Pick.AWAY):
        messages.error(request, 'Please choose the home or away team.')
        return redirect(back)

    # Optional confidence 1–3. Invalid values are ignored (treated as unset).
    confidence = request.POST.get('confidence') or None
    if confidence is not None:
        try:
            confidence = int(confidence)
            if confidence not in (Pick.CONFIDENCE_LEAN, Pick.CONFIDENCE_SOLID, Pick.CONFIDENCE_LOCK):
                confidence = None
        except (TypeError, ValueError):
            confidence = None

    # Enforced on the server. Hiding the button in the page isn't enough:
    # anyone can send the request by hand.
    if game.has_started:
        messages.error(request, f'Picks are locked for {game} (it has already started).')
        return redirect(back)

    # Picks can be changed any time before kickoff (the lock check above stops
    # changes once the game has started).
    defaults = {'team_picked': team_picked, 'confidence': confidence}
    pick, created = Pick.objects.update_or_create(
        user=request.user, game=game, defaults=defaults
    )
    team = _team_name(game, team_picked)
    verb = 'saved' if created else 'changed'
    conf_label = {1: ' (Lean)', 2: ' (Solid)', 3: ' (Lock)'}.get(confidence, '')
    messages.success(request, f'Pick {verb} for {game}: {team}{conf_label}.')
    return redirect(back)


@login_required
def friend_search(request):
    query = request.GET.get('q', '').strip()
    users = User.objects.none()

    if query:
        users = User.objects.filter(
            username__icontains=query
        ).exclude(
            pk=request.user.pk
        ).order_by('username')[:20]

    return render(request, 'accounts/friend_search.html', {
        'query': query,
        'users': users,
    })


@login_required
def send_friend_request(request, user_id):

    if request.method != 'POST':
        return redirect('dashboard')

    recipient = get_object_or_404(User, pk=user_id)

    if recipient == request.user:
        messages.error(request, "You cannot send a friend request to yourself.")
        return redirect('dashboard')

    existing_request = FriendRequest.objects.filter(
        sender=request.user,
        receiver=recipient,
    ).first()

    if existing_request:
        messages.info(request, "You've already sent this user a friend request.")
        return redirect('dashboard')

    reverse_request = FriendRequest.objects.filter(
        sender=recipient,
        receiver=request.user,
        status=FriendRequest.PENDING,
    ).first()

    if reverse_request:
        messages.info(
            request,
            "This user has already requested to be your friend. "
            "You can respond to their request when we add request management."
        )
        return redirect('dashboard')

    already_friends = FriendRequest.objects.filter(
        sender=request.user,
        receiver=recipient,
        status=FriendRequest.ACCEPTED,
    ).exists() or FriendRequest.objects.filter(
        sender=recipient,
        receiver=request.user,
        status=FriendRequest.ACCEPTED,
    ).exists()

    if already_friends:
        messages.info(request, "You're already friends with this user.")
        return redirect('dashboard')

    FriendRequest.objects.create(
        sender=request.user,
        receiver=recipient,
        status=FriendRequest.PENDING,
    )

    messages.success(
        request,
        f"Friend request sent to {recipient.username}."
    )
    return redirect('dashboard')


@login_required
def respond_friend_request(request, request_id, action):
    from django.contrib import messages
    from django.shortcuts import get_object_or_404, redirect
    from django.views.decorators.http import require_POST

    if request.method != 'POST':
        return redirect('dashboard')

    friend_request = get_object_or_404(
        FriendRequest,
        pk=request_id,
        receiver=request.user,
        status=FriendRequest.PENDING,
    )

    if action == 'accept':
        friend_request.status = FriendRequest.ACCEPTED
        friend_request.save(update_fields=['status'])
        messages.success(
            request,
            f"You and {friend_request.sender.username} are now friends."
        )

    elif action == 'decline':
        sender_username = friend_request.sender.username
        friend_request.delete()
        messages.success(
            request,
            f"Friend request from {sender_username} declined."
        )

    else:
        messages.error(request, "Invalid friend request action.")

    return redirect(f"{reverse('dashboard')}?friends=requests")


@login_required
@require_POST
def equip_title_view(request):
    from .titles import equip_title, available_titles
    title = (request.POST.get('title') or '').strip()
    if equip_title(request.user, title):
        if title:
            messages.success(request, f'Title equipped: {title}')
        else:
            messages.success(request, 'Title cleared.')
    else:
        messages.error(request, 'That title is not unlocked yet.')
    return redirect(request.POST.get('next') or 'profile')


@login_required
@require_POST
def react_to_game(request, game_id):
    """Post or update a live emoji reaction on a single game."""
    from .models import GameReaction
    game = get_object_or_404(Game, game_id=game_id)
    emoji = request.POST.get('emoji', '').strip()
    valid = dict(GameReaction.choices)
    if emoji not in valid:
        messages.error(request, 'Pick a valid reaction.')
        return redirect(request.POST.get('next') or 'dashboard')

    # Only allow reactions once the game has started (live energy, not pre-game spam).
    if not game.has_started:
        messages.error(request, 'Reactions open at kickoff.')
        return redirect(request.POST.get('next') or 'picks')

    GameReaction.objects.update_or_create(
        user=request.user,
        game=game,
        defaults={'emoji': emoji},
    )
    messages.success(request, f'Reacted {emoji} to {game.away_team} @ {game.home_team}.')
    next_url = request.POST.get('next') or reverse('picks') + f'?season={game.season}&week={game.week}'
    return redirect(next_url)


@login_required
def week_recap(request):
    """Post-week (or mid-week) recap of record, confidence, friends, highlights."""
    selected_season, seasons = _selected_season(request)
    try:
        week = int(request.GET.get('week', ''))
    except (TypeError, ValueError):
        week = current_week() if selected_season == settings.NFL_SEASON else default_week(selected_season)
    if week < 1 or week > 22:
        week = current_week()
    recap = build_week_recap(request.user, selected_season, week)
    return render(request, 'accounts/week_recap.html', {
        'recap': recap,
        'selected_season': selected_season,
        'seasons': seasons,
        'weeks': range(1, 19),
    })
