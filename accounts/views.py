# accounts/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from datetime import datetime, timedelta
from django.utils import timezone
from .forms import SignUpForm, LoginForm
from api.models import Game, NFLWeek, Score
from .models import Pick, UserStatistics

def signup_view(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)  # Log in the user after successful registration
            messages.success(request, 'Registration successful. Welcome!')
            return redirect('dashboard')  # Redirect to dashboard
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
            return redirect('dashboard')  # Redirect to dashboard
    else:
        form = LoginForm()
    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    logout(request)
    messages.success(request, 'You have been logged out.')
    return redirect('login')


@login_required
def dashboard(request):
    week_instance, _ = NFLWeek.objects.get_or_create(id=1)
    current_week = week_instance.current_week

    # Fetch all games for the current week
    games = Game.objects.filter(week=current_week).order_by('game_date')

    # Fetch scores
    scores = {score.game_id: score for score in Score.objects.all()}

    # Fetch picks for the current user
    user_picks = Pick.objects.filter(user=request.user).values('game_id', 'team_picked')

    # Create a dictionary to easily check picks
    user_picks_dict = {pick['game_id']: pick['team_picked'] for pick in user_picks}

    # Define the standard game start times
    start_times = {
        "Thursday": "20:00",  # 8:00 PM
        "Sunday": "13:00",    # 1:00 PM
        "Monday": "20:00"     # 8:00 PM
    }

    # Calculate winner for each game and determine pick availability
    game_data = []
    now = timezone.now()

    for game in games:
        score = scores.get(game.game_id)
        if score:
            if score.home_score > score.away_score:
                winner = game.home_team
            elif score.away_score > score.home_score:
                winner = game.away_team
            else:
                winner = "Draw"
        else:
            winner = "N/A"

        # Determine the pick status
        pick_status = user_picks_dict.get(game.game_id, "Not Picked")

        # Check if game_date is not None
        game_date = game.game_date
        if game_date:
            game_weekday = game_date.strftime("%A")  # Get the day of the week as a string

            # Determine the start time based on the game day
            game_start_time = start_times.get(game_weekday, "13:00")  # Default time (if any game is on a different day)

            # Create the datetime object for the game's start time
            game_datetime = datetime.strptime(f"{game_date} {game_start_time}", "%Y-%m-%d %H:%M")
            pick_available = now < timezone.make_aware(game_datetime)  # Convert to timezone-aware datetime
        else:
            # Handle cases where game_date is None (set pick availability to False or skip)
            game_datetime = None
            pick_available = False  # or set to True if you want to allow picks without a valid game date

        game_data.append({
            'game': game,
            'score': score,
            'winner': winner,
            'pick_status': pick_status,
            'pick_available': pick_available,
        })

    # Fetch user statistics
    user_stats, _ = UserStatistics.objects.get_or_create(user=request.user)

    context = {
        'current_week': current_week,
        'game_data': game_data,
        'user_stats': user_stats,
    }

    return render(request, 'accounts/dashboard.html', context)


@login_required
def make_pick(request, game_id):
    if request.method == 'POST':
        team_picked = request.POST.get('team_picked')
        game = get_object_or_404(Game, game_id=game_id)

        # Debugging: Check values
        print(f"User: {request.user}, Game: {game}, Team Picked: {team_picked}")

        # Save or update the pick
        pick, created = Pick.objects.update_or_create(
            user=request.user,
            game=game,
            defaults={'team_picked': team_picked}
        )

        # Debugging: Confirm pick was saved
        if created:
            print(f"Created new pick for user {request.user} and game {game_id}")
        else:
            print(f"Updated existing pick for user {request.user} and game {game_id}")

    return redirect('dashboard')


def get_game_winner(game):
    """
    Helper function to determine the winner of a game based on the score.
    """
    score = Score.objects.filter(game_id=game.game_id).first()
    if score:
        if score.home_score > score.away_score:
            return game.home_team
        elif score.away_score > score.home_score:
            return game.away_team
        else:
            return "Draw"
    return None


def update_user_statistics():
    # Fetch all games with results
    games = Game.objects.all()
    for game in games:
        # Get the winner from the score
        score = Score.objects.filter(game_id=game.game_id).first()
        if score:
            # Determine the game winner based on the score
            if score.home_score > score.away_score:
                game_winner = 'home'  # Changed to 'home'
            elif score.away_score > score.home_score:
                game_winner = 'away'  # Changed to 'away'
            else:
                game_winner = "Draw"

            # Fetch user picks for this game
            picks = Pick.objects.filter(game=game)
            for pick in picks:
                # Ensure UserStatistics exists for the user
                user_stats, created = UserStatistics.objects.get_or_create(user=pick.user)

                # Debugging: Check values
                print(f"Game: {game}, User: {pick.user}, Pick: {pick.team_picked}, Winner: {game_winner}")

                if game_winner == "Draw":
                    user_stats.ties += 1
                elif game_winner == pick.team_picked:  # This comparison should now be correct
                    user_stats.wins += 1
                else:
                    user_stats.losses += 1

                # Save the updated user statistics
                user_stats.save()
                print(f"Updated stats for user {pick.user}: Wins {user_stats.wins}, Losses {user_stats.losses}, Ties {user_stats.ties}")
