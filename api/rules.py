"""
Plain helper functions for the NFL pick'em site.

Nothing in here imports Django, so these functions are easy to test and easy
to reason about. They are the single source of truth for:

  * what counts as a finished game
  * whether a pick was a win, a loss, or a tie
  * when picks lock
  * which week is the "current" week
"""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

SCHEDULED = "scheduled"
LIVE = "live"
FINAL = "final"


def to_int(value):
    """'27' -> 27, '' / None / 'abc' -> None."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_status(raw):
    """
    Turn Tank01's status fields into one of: scheduled / live / final.

    Tank01 sends gameStatusCode: "0" not started, "1" in progress,
    "2" completed/final (anything else, e.g. "4" suspended, is NOT final).
    It also sends a text gameStatus such as "Completed" or "Live - In Progress".
    """
    code = str(raw.get("gameStatusCode", "")).strip()
    text = str(raw.get("gameStatus", "")).strip().lower()
    if code == "2" or text in ("completed", "final"):
        return FINAL
    if code == "1" or text.startswith("live"):
        return LIVE
    return SCHEDULED


def parse_kickoff(raw):
    """Kickoff as an aware UTC datetime from Tank01's gameTime_epoch, or None."""
    try:
        return datetime.fromtimestamp(float(raw.get("gameTime_epoch")), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def parse_game(raw):
    """One entry from getNFLGamesForWeek -> dict of Game fields, or None if unusable."""
    game_id = raw.get("gameID")
    home = raw.get("home")
    away = raw.get("away")
    date_str = raw.get("gameDate")
    if not (game_id and home and away and date_str):
        return None
    try:
        game_date = datetime.strptime(str(date_str), "%Y%m%d").date()
    except ValueError:
        return None
    return {
        "game_id": game_id,
        "home_team": home,
        "away_team": away,
        "game_date": game_date,
        "kickoff": parse_kickoff(raw),
    }


def parse_score(raw):
    """
    One entry from getNFLScoresOnly -> status and scores.

    A game is only reported as final if it has BOTH scores; otherwise we
    treat it as still live so a half-filled record can never be graded.
    """
    status = normalize_status(raw)
    home = to_int(raw.get("homePts"))
    away = to_int(raw.get("awayPts"))
    if status == FINAL and (home is None or away is None):
        status = LIVE
    return {"status": status, "home_score": home, "away_score": away}


def grade_pick(picked, home_score, away_score):
    """
    'win' / 'loss' / 'tie' for a pick ('home' or 'away'), or None if there is
    no score to grade against.
    """
    if home_score is None or away_score is None:
        return None
    if home_score == away_score:
        return "tie"
    winner = "home" if home_score > away_score else "away"
    return "win" if picked == winner else "loss"


def lock_time(kickoff, game_date):
    """
    The moment picks lock for a game: its real kickoff when we have it.
    If the API gave us no kickoff time, fall back to 9:00 AM Eastern on game
    day (before the earliest possible kickoff), so a pick can never slip in
    after a game has started.
    """
    if kickoff is not None:
        return kickoff
    return datetime.combine(game_date, time(9, 0), tzinfo=EASTERN)


def choose_current_week(games, today, stale_days=4):
    """
    games: iterable of (week, status, game_date).

    The current week is the lowest week that still has an unfinished game.
    An unfinished game more than `stale_days` old (postponed, cancelled, bad
    data) is ignored so it can't hold the whole site on an old week.
    If everything loaded is finished, stay on the latest loaded week.
    With nothing loaded yet, answer week 1.
    """
    games = list(games)
    if not games:
        return 1
    cutoff = today - timedelta(days=stale_days)
    open_weeks = [week for (week, status, game_date) in games
                  if status != FINAL and game_date >= cutoff]
    if open_weeks:
        return min(open_weeks)
    return max(week for (week, _status, _date) in games)
