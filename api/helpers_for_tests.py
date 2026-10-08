"""
Shared helpers for the test files. This is not a test file itself.

Nothing in the tests ever calls the real Tank01 API. FakeApi stands in for
api.services._get and records every call, so tests can also check that the
site does NOT spend API calls when it doesn't need to.
"""
import itertools
from datetime import timedelta

from django.utils import timezone

from api.models import Game
from api.services import ApiError

_ids = itertools.count(1)


def hours_from_now(hours):
    """A whole-second datetime (so it survives the epoch round trip exactly)."""
    return (timezone.now() + timedelta(hours=hours)).replace(microsecond=0)


def make_game(**overrides):
    """A 2026 week-1 game that kicks off tomorrow, with a fresh schedule stamp."""
    n = next(_ids)
    now = timezone.now()
    fields = {
        "season": 2026,
        "week": 1,
        "game_id": f"TEST{n:03d}_BAL@KC",
        "home_team": "KC",
        "away_team": "BAL",
        "game_date": timezone.localdate(),
        "kickoff": now + timedelta(days=1),
        "status": Game.SCHEDULED,
        "schedule_synced_at": now,
    }
    fields.update(overrides)
    return Game.objects.create(**fields)


def make_final(game, home_score, away_score):
    game.status = Game.FINAL
    game.home_score = home_score
    game.away_score = away_score
    game.save()
    return game


def raw_game(game_id, home, away, kickoff=None, game_date=None):
    """One entry the way getNFLGamesForWeek returns it."""
    if game_date is None:
        game_date = timezone.localtime(kickoff).date() if kickoff else timezone.localdate()
    raw = {
        "gameID": game_id,
        "home": home,
        "away": away,
        "gameDate": game_date.strftime("%Y%m%d"),
    }
    if kickoff is not None:
        raw["gameTime_epoch"] = str(kickoff.timestamp())
    return raw


def raw_score(code, home_pts, away_pts):
    """One entry the way getNFLScoresOnly returns it (code 0/1/2 = not started/live/final)."""
    return {
        "gameStatusCode": str(code),
        "homePts": "" if home_pts is None else str(home_pts),
        "awayPts": "" if away_pts is None else str(away_pts),
    }


class FakeApi:
    """Use as:  with patch('api.services._get', FakeApi(...)) as ..."""

    def __init__(self, schedules=None, scores=None, error=None):
        self.schedules = schedules or {}   # {week: [raw_game, ...]}
        self.scores = scores or {}         # {week: {game_id: raw_score}}
        self.error = error
        self.calls = []                    # [(endpoint, week), ...]

    def __call__(self, endpoint, params):
        self.calls.append((endpoint, params.get("week", params.get("gameWeek"))))
        if self.error:
            raise ApiError(self.error)
        if endpoint == "getNFLGamesForWeek":
            return self.schedules.get(params["week"], [])
        if endpoint == "getNFLScoresOnly":
            return self.scores.get(params["gameWeek"], {})
        raise AssertionError(f"Unexpected API endpoint: {endpoint}")
