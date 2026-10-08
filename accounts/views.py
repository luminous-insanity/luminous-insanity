# accounts/views.py

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from api.models import Game
from api.services import MAX_WEEK, current_week
from .forms import LoginForm, SignUpForm
from .models import Pick
from .standings import standing_for


def signup_view(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)  # Log in the user after successful registration
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


@login_required
def dashboard(request, week_number=None):
    current = current_week()
    selected_week = week_number or _selected_week(request, current)

    games = (Game.objects
             .filter(season=settings.NFL_SEASON, week=selected_week)
             .order_by('game_date', 'kickoff', 'id'))

    # {Game primary key: 'home' or 'away'}. (The old code keyed this by the
    # wrong id, so the dashboard never showed anyone's existing picks.)
    picks = {p.game_id: p.team_picked
             for p in Pick.objects.filter(user=request.user, game__in=games)}

    game_data = []
    for game in games:
        has_scores = game.home_score is not None and game.away_score is not None
        game_data.append({
            'game': game,
            # The Game itself carries home_score / away_score, so templates
            # that use item.score.home_score keep working.
            'score': game if has_scores else None,
            'winner': game.winner_name or 'N/A',
            'pick_status': picks.get(game.pk, 'Not Picked'),
            'pick_team': _team_name(game, picks.get(game.pk)),
            'pick_available': not game.has_started,
        })

    context = {
        'current_week': current,
        'selected_week': selected_week,
        'game_data': game_data,
        'user_stats': standing_for(request.user),
    }
    return render(request, 'accounts/dashboard.html', context)


@login_required
@require_POST
def make_pick(request, game_id):
    game = get_object_or_404(Game, game_id=game_id)
    back = f"{reverse('dashboard')}?week={game.week}"

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
