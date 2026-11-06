"""Confidence Points — optional depth on top of W-L-T.

Correct picks award confidence points equal to the confidence level (1–3).
Underdog correct locks award a +1 bonus when team records are available.
W-L-T standings are never changed by confidence.
"""
import logging

from api.models import Game
from api.rules import grade_pick
from .models import Pick

log = logging.getLogger(__name__)


def is_underdog_pick(pick, team_records):
    """True if the picked team has a worse win% than the opponent (when known)."""
    if not team_records or not isinstance(team_records, dict):
        return False
    game = getattr(pick, 'game', None)
    if game is None:
        return False
    home_team = getattr(game, 'home_team', None) or ''
    away_team = getattr(game, 'away_team', None) or ''
    home_rec = team_records.get(home_team) or team_records.get(str(home_team).upper())
    away_rec = team_records.get(away_team) or team_records.get(str(away_team).upper())
    if not isinstance(home_rec, dict) or not isinstance(away_rec, dict):
        return False

    def pct(rec):
        try:
            w = int(rec.get('wins') or rec.get('W') or 0)
            l = int(rec.get('losses') or rec.get('L') or 0)
            t = int(rec.get('ties') or rec.get('T') or 0)
        except (TypeError, ValueError):
            return 0.5
        n = w + l + t
        return (w + 0.5 * t) / n if n else 0.5

    home_pct = pct(home_rec)
    away_pct = pct(away_rec)
    if pick.team_picked == Pick.HOME:
        return home_pct < away_pct
    return away_pct < home_pct


def confidence_points_for_user(user, season=None, week=None, team_records=None):
    """Sum confidence points from graded correct picks."""
    qs = Pick.objects.filter(
        user=user,
        game__status=Game.FINAL,
        game__home_score__isnull=False,
        game__away_score__isnull=False,
        confidence__isnull=False,
    ).select_related('game')
    if season is not None:
        qs = qs.filter(game__season=season)
    if week is not None:
        qs = qs.filter(game__week=week)

    total = 0
    underdog_locks = 0
    for pick in qs:
        try:
            outcome = grade_pick(pick.team_picked, pick.game.home_score, pick.game.away_score)
            if outcome != 'win':
                continue
            pts = pick.confidence or 0
            if pick.confidence == Pick.CONFIDENCE_LOCK and is_underdog_pick(pick, team_records):
                pts += 1
                underdog_locks += 1
            total += pts
        except Exception:
            # Skip any single pick that cannot be graded rather than failing the whole board
            log.exception("Could not grade pick %s", getattr(pick, 'pk', None))
            continue
    return {'points': total, 'underdog_locks': underdog_locks}
