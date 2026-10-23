# accounts/views.py

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from datetime import timedelta
from django.utils import timezone
from api.models import Game
from api.services import MAX_WEEK, current_week, get_team_records
from .forms import LoginForm, SignUpForm
from .models import Pick
import logging
from .standings import standing_for


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

    try:
        season = int(request.GET.get('season', settings.NFL_SEASON))
    except (TypeError, ValueError):
        season = settings.NFL_SEASON

    if season not in seasons:
        season = settings.NFL_SEASON

    return season, seasons


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

    context = {
        'user_stats': user_stats,
        'record_week': record_week,
        'weeks': range(1, MAX_WEEK + 1),
        'selected_season': selected_season,
        'seasons': seasons,
    }

    return render(request, 'accounts/dashboard.html', context)


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

    picks_by_game = {
        p.game_id: p.team_picked
        for p in Pick.objects.filter(
            user=request.user,
            game__in=games,
            game__season=selected_season,
        )
    }

    game_data = []
    for game in games:
        has_scores = game.is_final
        game_data.append({
            'game': game,
            'kickoff_label': get_kickoff_label(game),
            'score': game if has_scores else None,
            'winner': game.winner_name or 'N/A',
            'pick_status': picks_by_game.get(game.pk, 'Not Picked'),
            'pick_team': _team_name(game, picks_by_game.get(game.pk)),
            'pick_available': not game.has_started,
            'home_record': team_records.get(game.home_team),
            'away_record': team_records.get(game.away_team),
        })

    context = {
        'current_week': current,
        'selected_week': selected_week,
        'game_data': game_data,
        'selected_season': selected_season,
        'seasons': seasons,
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

    # Enforced on the server. Hiding the button in the page isn't enough:
    # anyone can send the request by hand.
    if game.has_started:
        messages.error(request, f'Picks are locked for {game} (it has already started).')
        return redirect(back)

    # Picks can be changed any time before kickoff (the lock check above stops
    # changes once the game has started).
    pick, created = Pick.objects.update_or_create(
        user=request.user, game=game, defaults={'team_picked': team_picked}
    )
    team = _team_name(game, team_picked)
    verb = 'saved' if created else 'changed'
    messages.success(request, f'Pick {verb} for {game}: {team}.')
    return redirect(back)
