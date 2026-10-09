# api/services.py
"""
Schedule + score syncing.

The golden rule: running a sync twice does the same thing as running it once.
Nothing here deletes games (which would delete everyone's picks) and nothing
here adds to a running total. Standings are always recalculated from the picks
and the final scores (see accounts/standings.py).

API usage is kept small on purpose:
  * a score call only happens when a game has started and isn't final yet,
    and never more than once every 10 minutes per game
  * the schedule for a week is loaded once, then refreshed at most once a day
So you can call run_sync() as often as you like; it only spends API calls
when there is something to learn.
"""
import logging
from datetime import timedelta

import requests
from django.conf import settings
from django.db.models import Max, Q
from django.utils import timezone

from . import rules
from .models import Game

log = logging.getLogger(__name__)

MAX_WEEK = 18            # regular season
REQUEST_TIMEOUT = 15     # seconds; never let a hung request freeze the site
LIVE_RECHECK = timedelta(minutes=10)
STALE_RECHECK = timedelta(hours=24)
LIVE_WINDOW = timedelta(hours=8)     # how long after kickoff we poll often
EXPECTED_LENGTH = timedelta(hours=5)  # NFL games run about 3.5 hours; leave margin
GIVE_UP_AFTER_DAYS = 14              # stop auto-polling games this old


class ApiError(Exception):
    pass


def _get(endpoint, params):
    url = f"https://{settings.NFL_API_HOST}/{endpoint}"
    headers = {
        "x-rapidapi-key": settings.NFL_API_KEY,
        "x-rapidapi-host": settings.NFL_API_HOST,
    }
    try:
        response = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise ApiError(f"{endpoint} failed: {exc}") from exc
    body = data.get("body") if isinstance(data, dict) else None
    if body is None:
        raise ApiError(f"{endpoint} returned no 'body' (bad key, plan limit, or API change?)")
    return body


# ---------------------------------------------------------------- schedule --

def sync_schedule(week):
    """
    Load or refresh one week's games. Existing games are updated in place
    (matched on game_id) so picks are never lost. Scores/status are left alone.
    Returns (games_seen, games_with_kickoff_time).
    """
    body = _get("getNFLGamesForWeek", {
        "week": week, "seasonType": "reg", "season": settings.NFL_SEASON,
    })
    raw_games = body if isinstance(body, list) else []
    now = timezone.now()
    seen = with_kickoff = 0
    for raw in raw_games:
        parsed = rules.parse_game(raw)
        if parsed is None:
            log.warning("Skipping unusable game entry: %r", raw)
            continue
        game_id = parsed.pop("game_id")
        defaults = {
            "season": settings.NFL_SEASON,
            "week": week,
            "home_team": parsed["home_team"],
            "away_team": parsed["away_team"],
            "game_date": parsed["game_date"],
            "schedule_synced_at": now,
        }
        if parsed["kickoff"] is not None:      # never overwrite a known time with "unknown"
            defaults["kickoff"] = parsed["kickoff"]
            with_kickoff += 1
        Game.objects.update_or_create(game_id=game_id, defaults=defaults)
        seen += 1
    return seen, with_kickoff


# ------------------------------------------------------------------ scores --

def sync_scores(week):
    """
    One API call returns every game in the week. Save status and scores for
    each game we know about. Returns how many games in the week are final.
    """
    body = _get("getNFLScoresOnly", {
        "gameWeek": week, "seasonType": "reg", "season": settings.NFL_SEASON,
    })
    if not isinstance(body, dict):
        return 0
    now = timezone.now()
    final_count = 0
    for game_id, raw in body.items():
        parsed = rules.parse_score(raw)
        Game.objects.filter(game_id=game_id).update(
            status=parsed["status"],
            home_score=parsed["home_score"],
            away_score=parsed["away_score"],
            scores_checked_at=now,
        )
        if parsed["status"] == rules.FINAL:
            final_count += 1
    return final_count


def games_needing_scores(now=None):
    """Started, not final, and not checked too recently."""
    now = now or timezone.now()
    oldest = timezone.localdate() - timedelta(days=GIVE_UP_AFTER_DAYS)
    candidates = (Game.objects
                  .filter(season=settings.NFL_SEASON, game_date__gte=oldest)
                  .exclude(status=Game.FINAL))
    needed = []
    for game in candidates:
        started = game.lock_at
        if now < started:
            continue                                   # hasn't kicked off
        checked = game.scores_checked_at
        if checked is None:
            needed.append(game)
            continue
        # If our last look happened before the game could have finished (for
        # example a run at 11:45 PM caught it mid-game), the next run must look
        # again, however much later it is. This is what makes a schedule with
        # only a few runs a week work.
        looked_too_early = checked < started + EXPECTED_LENGTH
        if now - started <= LIVE_WINDOW or looked_too_early:
            wait = LIVE_RECHECK
        else:
            wait = STALE_RECHECK     # still unfinished long after it should have ended
        if checked < now - wait:
            needed.append(game)
    return needed


# ------------------------------------------------------------ current week --

def current_week():
    rows = (Game.objects.filter(season=settings.NFL_SEASON)
            .values_list("week", "status", "game_date"))
    return rules.choose_current_week(rows, timezone.localdate())


# ---------------------------------------------------------------- run_sync --

def run_sync():
    """
    Everything the site needs, in a few small steps. Safe to call any time,
    any number of times. Returns a dict describing what happened.
    """
    report = {"schedule_weeks": [], "score_weeks": [], "final_games": 0, "errors": []}

    def attempt(label, func, *args):
        try:
            return func(*args)
        except ApiError as exc:
            log.error("%s: %s", label, exc)
            report["errors"].append(f"{label}: {exc}")
            return None

    games = Game.objects.filter(season=settings.NFL_SEASON)

    # 1. Very first run of the season: load week 1.
    if not games.exists():
        if attempt("schedule week 1", sync_schedule, 1) is not None:
            report["schedule_weeks"].append(1)

    # 2. Grade anything that has kicked off and isn't final yet.
    for week in sorted({g.week for g in games_needing_scores()}):
        count = attempt(f"scores week {week}", sync_scores, week)
        if count is not None:
            report["score_weeks"].append(week)
            report["final_games"] += count

    # 3. When the latest loaded week is completely finished, open the next one.
    latest = games.aggregate(latest=Max("week"))["latest"]
    if (latest and latest < MAX_WEEK
            and not games.filter(week=latest).exclude(status=Game.FINAL).exists()):
        if attempt(f"schedule week {latest + 1}", sync_schedule, latest + 1) is not None:
            report["schedule_weeks"].append(latest + 1)

    # 4. Refresh the current week's schedule once a day (flex scheduling
    #    can move kickoff times, and kickoff time decides when picks lock).
    week = current_week()
    if week not in report["schedule_weeks"]:
        this_week = games.filter(week=week)
        stale = this_week.filter(
            Q(schedule_synced_at__isnull=True)
            | Q(schedule_synced_at__lt=timezone.now() - timedelta(hours=24))
        )
        if this_week.exists() and stale.exists():
            if attempt(f"schedule week {week}", sync_schedule, week) is not None:
                report["schedule_weeks"].append(week)

    report["current_week"] = current_week()
    return report
