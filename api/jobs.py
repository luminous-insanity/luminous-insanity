from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django_apscheduler.jobstores import DjangoJobStore, register_events
from accounts.views import update_user_statistics
import http.client
import json
from datetime import datetime, timedelta
from .models import NFLWeek, Game, Score

def fetch_nfl_games_and_increment_week():
    # Get or create the NFLWeek instance
    week_instance, created = NFLWeek.objects.get_or_create(id=1)

    week_instance.current_week += 1
    week_instance.save()

    current_week = week_instance.current_week

    conn = http.client.HTTPSConnection("tank01-nfl-live-in-game-real-time-statistics-nfl.p.rapidapi.com")
    headers = {
        'x-rapidapi-key': "c3108cef0fmsh47e07b4b8f82776p11b689jsn2e687e11c23d",
        'x-rapidapi-host': "tank01-nfl-live-in-game-real-time-statistics-nfl.p.rapidapi.com"
    }

    url = f"/getNFLGamesForWeek?week={current_week}&seasonType=reg&season=2024"
    conn.request("GET", url, headers=headers)

    res = conn.getresponse()
    data = res.read()

    # Decode the JSON response
    json_data = json.loads(data.decode("utf-8"))

    # Print the JSON data for debugging
    print("Fetched JSON data:", json_data)

    # Clear previous games for the week (optional)
    Game.objects.filter(week=current_week).delete()

    # Iterate over the games in the response and save them to the database
    for game in json_data.get('body', []):  # Change to 'body' if that's where games are
        game_id = game.get('gameID')
        home_team = game.get('home')
        away_team = game.get('away')
        game_date = game.get('gameDate')

        try:
            Game.objects.create(
                week=current_week,
                game_id=game_id,
                home_team=home_team,
                away_team=away_team,
                game_date=datetime.strptime(game_date, "%Y%m%d").date(),
            )
        except Exception as e:
            print(f"Error saving game {game_id}: {e}")

    print(f"Week {current_week} games stored successfully.")


def fetch_game_scores():
    # Determine the game date for fetching scores based on the current day
    today = datetime.now()
    current_weekday = today.weekday()  # Monday is 0 and Sunday is 6

    # Calculate the game date dynamically
    if current_weekday == 0:  # Monday
        game_date = (today - timedelta(days=1)).strftime("%Y%m%d")
    elif current_weekday == 1:  # Tuesday
        game_date = (today - timedelta(days=1)).strftime("%Y%m%d")
    elif current_weekday == 4:  # Friday
        game_date = (today - timedelta(days=1)).strftime("%Y%m%d")
    else:
        game_date = today.strftime("%Y%m%d")

    print(f"Fetching scores for game date: {game_date}")

    conn = http.client.HTTPSConnection("tank01-nfl-live-in-game-real-time-statistics-nfl.p.rapidapi.com")
    headers = {
        'x-rapidapi-key': "c3108cef0fmsh47e07b4b8f82776p11b689jsn2e687e11c23d",
        'x-rapidapi-host': "tank01-nfl-live-in-game-real-time-statistics-nfl.p.rapidapi.com"
    }

    conn.request("GET", f"/getNFLScoresOnly?gameDate={game_date}&topPerformers=true", headers=headers)

    res = conn.getresponse()
    data = res.read()
    json_data = json.loads(data.decode("utf-8"))

    print("API Response:", json_data)

    if isinstance(json_data, dict) and 'body' in json_data:
        scores_data = json_data['body']
        for game_id, game_details in scores_data.items():
            # Extract scores
            home_pts = game_details.get('homePts')
            away_pts = game_details.get('awayPts')

            print(f"Game ID: {game_id}, Home Score: {home_pts}, Away Score: {away_pts}")

            # Convert scores to integers and handle potential conversion errors
            try:
                home_score = int(home_pts)
                away_score = int(away_pts)
            except (ValueError, TypeError):
                print(f"Invalid score data: homePts={home_pts}, awayPts={away_pts}")
                continue

            # Update or create a new score entry
            Score.objects.update_or_create(
                game_id=game_id,
                defaults={'home_score': home_score, 'away_score': away_score, 'game_date': game_date}
            )

    print(f"Scores for games on {game_date} updated successfully.")
    update_user_statistics()


def start():
    scheduler = BackgroundScheduler()
    scheduler.add_jobstore(DjangoJobStore(), "default")

    # Schedule the fetch for games
    scheduler.add_job(
        fetch_nfl_games_and_increment_week,
        trigger=CronTrigger(day_of_week="tue", hour=0, minute=1),
        id="fetch_nfl_games_and_increment_week",
        max_instances=1,
        replace_existing=True,
    )

    # Schedule the fetch for scores
    scheduler.add_job(
        fetch_game_scores,
        trigger=CronTrigger(day_of_week="fri", hour=0, minute=1),
        id="fetch_game_scores_friday",
        max_instances=1,
        replace_existing=True,
    )
    scheduler.add_job(
        fetch_game_scores,
        trigger=CronTrigger(day_of_week="mon", hour=0, minute=1),
        id="fetch_game_scores_monday",
        max_instances=1,
        replace_existing=True,
    )
    scheduler.add_job(
        fetch_game_scores,
        trigger=CronTrigger(day_of_week="tue", hour=0, minute=1),
        id="fetch_game_scores_tuesday",
        max_instances=1,
        replace_existing=True,
    )

    register_events(scheduler)
    scheduler.start()
    print("Scheduler started with jobs to fetch NFL games and scores.")