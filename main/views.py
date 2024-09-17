# views.py
from django.shortcuts import render
from accounts.models import UserStatistics, Pick
from api.models import Game
from django.contrib.auth.decorators import login_required


def home(request):
    # Fetch all user statistics and order by wins in descending order
    user_stats = UserStatistics.objects.filter(user__is_superuser=False).order_by('-wins')

    context = {
        'user_stats': user_stats,
    }

    return render(request, 'main/home.html', context)


@login_required
def history_view(request):
    # Fetch all games
    games = Game.objects.all().order_by('game_date')

    # Fetch picks for the current user
    user_picks = Pick.objects.filter(user=request.user).values('game_id', 'team_picked')
    user_picks_dict = {pick['game_id']: pick['team_picked'] for pick in user_picks}

    # Prepare game data with user picks
    game_data = []
    for game in games:
        game_data.append({
            'game': game,
            'user_pick': user_picks_dict.get(game.game_id, 'Not Picked')
        })

    context = {
        'game_data': game_data,
    }

    return render(request, 'main/history.html', context)