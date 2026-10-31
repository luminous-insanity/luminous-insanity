"""HTTP surface for CROSSFIRE — isolated from core picks / standings views."""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from api.models import Game
from api.services import current_week

from .crossfire import (
    CrossfireError,
    fire_targets_for_game,
    place_crossfire,
    cancel_crossfire,
    season_sharpshooters,
    tokens_left,
    week_board,
)
from .models import Crossfire, Pick


@login_required
def crossfire_board(request):
    season = settings.NFL_SEASON
    try:
        week = int(request.GET.get('week') or current_week())
    except (TypeError, ValueError):
        week = current_week()
    board = week_board(season, week, viewer=request.user)
    season_leaders = season_sharpshooters(season)
    # Weeks that have any crossfire activity + current week for the switcher
    active_weeks = sorted(set(
        Crossfire.objects.filter(season=season).values_list('week', flat=True)
    ) | {week})
    return render(request, 'accounts/crossfire.html', {
        'page': 'crossfire',
        'board': board,
        'season_leaders': season_leaders,
        'active_weeks': active_weeks,
        'selected_week': week,
        'selected_season': season,
    })


@login_required
def crossfire_aim(request, game_id):
    """Choose a target for a crossfire on one open game."""
    game = get_object_or_404(Game, game_id=game_id)
    if game.has_started:
        messages.error(request, 'That game has already locked.')
        return redirect('crossfire')
    try:
        my_pick = Pick.objects.get(user=request.user, game=game)
    except Pick.DoesNotExist:
        messages.error(request, 'Make your own pick on this game first.')
        return redirect(f"{reverse('picks')}?week={game.week}")

    targets = fire_targets_for_game(request.user, game)
    left = tokens_left(request.user, game.season, game.week)
    return render(request, 'accounts/crossfire_aim.html', {
        'page': 'crossfire',
        'game': game,
        'my_pick': my_pick,
        'targets': targets,
        'tokens_left': left,
    })


@login_required
@require_POST
def crossfire_fire(request, game_id, user_id):
    game = get_object_or_404(Game, game_id=game_id)
    from django.contrib.auth.models import User
    target = get_object_or_404(User, pk=user_id)
    try:
        cf = place_crossfire(request.user, target, game)
    except CrossfireError as exc:
        messages.error(request, str(exc))
        return redirect('crossfire_aim', game_id=game_id)
    messages.success(
        request,
        f"Crossfire locked on {target.username} for "
        f"{game.away_team} @ {game.home_team}."
    )
    return redirect(f"{reverse('crossfire')}?week={cf.week}")


@login_required
@require_POST
def crossfire_cancel(request, crossfire_id):
    try:
        cancel_crossfire(request.user, crossfire_id)
        messages.success(request, 'Crossfire cancelled.')
    except CrossfireError as exc:
        messages.error(request, str(exc))
    week = request.POST.get('week') or current_week()
    return redirect(f"{reverse('crossfire')}?week={week}")
