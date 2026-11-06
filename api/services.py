# api/services.py
"""
Schedule + score syncing.

The golden rule: running a sync twice does the same thing as running it once.
Nothing here deletes games (which would delete everyone's picks) and nothing
here adds to a running total. Standings are always recalculated from the picks
and the final scores (see accounts/standings.py).

API usage is kept small on purpose:
  * a score call only happens when a game has started and isn't final yet,
    and never more than once every 15 minutes per game (aligned with a
    typical free cron interval so live scores stay fresh without fighting
    the scheduler)
  * the schedule for a week is loaded once, then refreshed at most once a day
So you can call run_sync() as often as you like; it only spends API calls
when there is something to learn.
"""
import logging
from datetime import timedelta

import requests
from django.conf import settings
from django.db.models import Count, Max, Q
from django.utils import timezone

from . import rules
from .models import Game
from django.core.cache import cache

log = logging.getLogger(__name__)

REGULAR_SEASON_MAX_WEEK = 18
REGULAR_SEASON_GAMES_PER_WEEK = 16
FIRST_PLAYOFF_WEEK = 19
PLAYOFF_ROUNDS = 4
# NFL postseason games per elimination round: Wild Card, Divisional, Conference.
PLAYOFF_GAMES_PER_CUT = {1: 6, 2: 4, 3: 2}
MAX_WEEK = FIRST_PLAYOFF_WEEK + PLAYOFF_ROUNDS - 1  # 22
REQUEST_TIMEOUT = 15     # seconds; never let a hung request freeze the site
LIVE_RECHECK = timedelta(minutes=15)  # match free cron-job.org interval; cache live scores this long
STALE_RECHECK = timedelta(hours=24)
LIVE_WINDOW = timedelta(hours=8)     # how long after kickoff we poll often
EXPECTED_LENGTH = timedelta(hours=5)  # NFL games run about 3.5 hours; leave margin
GIVE_UP_AFTER_DAYS = 14              # stop auto-polling games this old


class ApiError(Exception):
    pass


def _week_api_params(week, endpoint):
    """
    Translate GameDayPicks weeks into Tank01 API parameters.

    Internal weeks 1-18 are regular season.
    Internal weeks 19-22 are postseason rounds 1-4.
    """
    if 1 <= week <= REGULAR_SEASON_MAX_WEEK:
        season_type = "reg"
        api_week = week
    elif FIRST_PLAYOFF_WEEK <= week <= MAX_WEEK:
        season_type = "post"
        api_week = week - FIRST_PLAYOFF_WEEK + 1
    else:
        raise ApiError(f"Unsupported GameDayPicks week: {week}")

    if endpoint == "getNFLGamesForWeek" and season_type == "post":
        week_param = "gameWeek"
    elif endpoint == "getNFLGamesForWeek":
        week_param = "week"
    else:
        week_param = "gameWeek"

    return {
        week_param: api_week,
        "seasonType": season_type,
        "season": settings.NFL_SEASON,
    }


def _get(endpoint, params, timeout=None):
    url = f"https://{settings.NFL_API_HOST}/{endpoint}"
    headers = {
        "x-rapidapi-key": settings.NFL_API_KEY,
        "x-rapidapi-host": settings.NFL_API_HOST,
    }
    try:
        response = requests.get(
            url, headers=headers, params=params,
            timeout=timeout or REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise ApiError(f"{endpoint} failed: {exc}") from exc
    body = data.get("body") if isinstance(data, dict) else None
    if body is None:
        raise ApiError(f"{endpoint} returned no 'body' (bad key, plan limit, or API change?)")
    return body


TEAM_RECORDS_FAIL_TTL = 300      # seconds to remember a failed lookup
TEAM_RECORDS_TIMEOUT = 4         # seconds; this runs while a page is rendering


def get_team_records():
    """Fetch NFL team records, cached 24h. Never blocks page loads for long.

    A failed or empty lookup is cached for a few minutes so a slow or
    rate-limited API cannot make every page view wait on it (504s).
    Always returns a dict (empty when records are unavailable).
    """
    cache_key = "nfl_team_records"
    cached_records = cache.get(cache_key)
    if cached_records is not None:
        return cached_records

    try:
        teams = _get("getNFLTeams", {}, timeout=TEAM_RECORDS_TIMEOUT)
        if not isinstance(teams, list):
            raise ApiError("getNFLTeams returned an unexpected response.")
    except ApiError as exc:
        log.warning(
            "Team records unavailable, using none for %ss: %s",
            TEAM_RECORDS_FAIL_TTL, exc,
        )
        cache.set(cache_key, {}, TEAM_RECORDS_FAIL_TTL)
        return {}

    records = {}
    for team in teams:
        if not isinstance(team, dict):
            continue
        team_abbr = team.get("teamAbv")
        if not team_abbr:
            continue
        records[team_abbr] = {
            "wins": team.get("wins", 0),
            "losses": team.get("loss", 0),
            "ties": team.get("tie", 0),
        }

    cache.set(cache_key, records, 86400 if records else TEAM_RECORDS_FAIL_TTL)
    return records


# ---------------------------------------------------------------- schedule --

def sync_schedule(week):
    """
    Load or refresh one week's games. Existing games are updated in place
    (matched on game_id) so picks are never lost. Scores/status are left alone.
    Returns (games_seen, games_with_kickoff_time).
    """
    body = _get(
        "getNFLGamesForWeek",
        _week_api_params(week, "getNFLGamesForWeek"),
    )
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
    body = _get(
        "getNFLScoresOnly",
        _week_api_params(week, "getNFLScoresOnly"),
    )
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



def _regular_season_ready_for_playoffs(season):
    """Require all 18 regular-season weeks and every game to be final.

    Qualification rules remain owned by accounts.playoffs / the existing
    capacity algorithm. This is an additional automation safety gate so a
    partially loaded season cannot be mistaken for a completed season.
    """
    regular = Game.objects.filter(
        season=season, week__gte=1, week__lte=REGULAR_SEASON_MAX_WEEK,
    )
    week_counts = dict(
        regular.values_list("week").annotate(game_count=Count("id"))
    )
    if any(
        week_counts.get(week) != REGULAR_SEASON_GAMES_PER_WEEK
        for week in range(1, REGULAR_SEASON_MAX_WEEK + 1)
    ):
        return False
    return not regular.exclude(
        status=Game.FINAL, home_score__isnull=False, away_score__isnull=False,
    ).exists()


def _process_playoff_lifecycle(report):
    """Automatically freeze the field and apply completed-round cuts.

    This calls the same open_playoffs() and run_cut() functions used by the
    staff management command. It does not implement or alter qualification,
    ranking, cut targets, or tiebreak rules.
    """
    from accounts.models import PlayoffEntry
    from accounts.playoff_rounds import (
        CUTS, PlayoffError, get_config, open_playoffs, run_cut,
    )

    season = settings.NFL_SEASON
    report.setdefault("playoff_actions", [])

    if not PlayoffEntry.objects.filter(season=season).exists():
        if not _regular_season_ready_for_playoffs(season):
            return
        try:
            entrants = open_playoffs(season)
        except PlayoffError as exc:
            # Not ready / no qualified players is a normal state during sync.
            log.info("Automatic playoff opening deferred for %s: %s", season, exc)
            return
        report["playoff_actions"].append({
            "action": "opened", "season": season, "entrants": entrants,
        })

    config = get_config(season)
    while config.rounds_cut < CUTS:
        round_no = config.rounds_cut + 1
        week = config.first_playoff_week + round_no - 1
        round_games = Game.objects.filter(season=season, week=week)

        # Require the complete NFL round schedule, not merely all currently
        # loaded games to be final (which could cut early on a partial feed).
        expected = PLAYOFF_GAMES_PER_CUT.get(round_no)
        if expected is None or round_games.count() != expected:
            break
        if round_games.exclude(
            status=Game.FINAL, home_score__isnull=False, away_score__isnull=False,
        ).exists():
            break

        try:
            result = run_cut(season)
        except PlayoffError as exc:
            log.info("Automatic playoff cut %s deferred for %s: %s", round_no, season, exc)
            break
        report["playoff_actions"].append({
            "action": "cut", "season": season, "round": result["round"],
            "round_name": result["round_name"], "before": result["before"],
            "after": result["after"], "eliminated": result["cut"],
        })
        config.refresh_from_db(fields=["rounds_cut", "first_playoff_week"])


# ---------------------------------------------------------------- run_sync --

def run_sync():
    """
    Everything the site needs, in a few small steps. Safe to call any time,
    any number of times. Returns a dict describing what happened.
    """
    report = {
        "schedule_weeks": [], "score_weeks": [], "final_games": 0,
        "errors": [], "playoff_actions": [],
    }

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

    if (latest
            and latest < MAX_WEEK
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

    # 5. Freeze the existing qualification result and process any fully
    # completed playoff rounds. Safe to retry on every scheduled sync.
    _process_playoff_lifecycle(report)

    report["current_week"] = current_week()
    return report
