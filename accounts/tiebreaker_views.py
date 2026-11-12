"""Save a player's "The Score is Right" guess from the picks page."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from api.models import Game

from . import tiebreaker
from .ratelimit import ratelimit


@login_required
@require_POST
@ratelimit('tiebreaker', limit=60, window=600, key='user', fallback='picks')
def tiebreaker_save(request, game_id):
    game = get_object_or_404(Game, game_id=game_id)
    back = f"{reverse('picks')}?season={game.season}&week={game.week}"
    expected = tiebreaker.tiebreaker_game(game.season, game.week)
    if expected is None or expected.pk != game.pk:
        messages.error(request, 'That game is not this week\u2019s tiebreaker.')
        return redirect(back)
    try:
        pick = tiebreaker.save_guess(request.user, game, request.POST.get('total_points', ''))
    except tiebreaker.TiebreakerError as exc:
        messages.error(request, exc.message)
        return redirect(back)
    messages.success(request, f'Tiebreaker guess saved: {pick.total_points} total points.')
    return redirect(back)
