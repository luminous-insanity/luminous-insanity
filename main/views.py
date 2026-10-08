# main/views.py
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from accounts.models import Pick
from accounts.standings import compute_standings
from api.models import Game
from api.rules import grade_pick


def home(request):
    # Calculated live from picks and final scores; same numbers as everywhere else.
    return render(request, 'main/home.html', {'user_stats': compute_standings()})


@login_required
def history_view(request):
    games = (Game.objects.filter(season=settings.NFL_SEASON)
             .order_by('game_date', 'kickoff', 'id'))
    user_picks = {
        pick['game__game_id']: pick['team_picked']
        for pick in Pick.objects.filter(user=request.user).values('game__game_id', 'team_picked')
    }

    outcome_labels = {'win': 'Win', 'loss': 'Loss', 'tie': 'Draw'}
    game_data = []
    for game in games:
        user_pick = user_picks.get(game.game_id, 'Not Picked')
        if user_pick == 'Not Picked':
            result = 'Not Picked'
        elif not game.is_final:
            result = 'Pending'
        else:
            outcome = grade_pick(user_pick, game.home_score, game.away_score)
            result = outcome_labels.get(outcome, 'Pending')
        game_data.append({'game': game, 'user_pick': user_pick, 'result': result})

    return render(request, 'main/history.html', {'game_data': game_data})
