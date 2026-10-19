# main/views.py
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from accounts.models import Pick
from accounts.views import _selected_season
from accounts.standings import compute_standings
from api.models import Game
from api.rules import grade_pick
from api.services import current_week


def home(request):
    current = current_week()

    games = (
        Game.objects
        .filter(season=settings.NFL_SEASON, week=current)
        .order_by('game_date', 'kickoff', 'id')[:6]
    )

    standings = compute_standings()[:3]

    return render(request, 'main/home.html', {
        'featured_games': games,
        'current_week': current,
        'top_standings': standings,
    })


def leaderboard(request):
    current = current_week()
    selected_season, seasons = _selected_season(request)

    selected_week = request.GET.get('week', 'season')

    if selected_week == 'season':
        user_stats = compute_standings(season=selected_season)
    else:
        try:
            selected_week = int(selected_week)
            if not 1 <= selected_week <= 18:
                selected_week = 'season'
        except (TypeError, ValueError):
            selected_week = 'season'

        if selected_week == 'season':
            user_stats = compute_standings(season=selected_season)
        else:
            user_stats = compute_standings(
                week=selected_week,
                season=selected_season,
            )

    return render(
        request,
        'main/leaderboard.html',
        {
            'user_stats': user_stats,
            'selected_week': selected_week,
            'current_week': current,
            'weeks': range(1, 19),
            'selected_season': selected_season,
            'seasons': seasons,
        }
    )



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


@login_required
def profile(request):
    return render(request, 'main/profile.html')


def about(request):
    return render(request, 'main/about.html')


def contact(request):
    return render(request, 'main/contact.html')


def privacy(request):
    return render(request, 'main/privacy.html')


def terms(request):
    return render(request, 'main/terms.html')
