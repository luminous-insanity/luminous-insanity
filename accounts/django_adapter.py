"""
Django integration layer for the pure playoff_qualification module.

This file shows exactly how to wire the new algorithm into the existing
GameDayPicks models and views.  It is deliberately written so you can
copy pieces into accounts/playoffs.py (or keep it as a parallel module
and call it from championship_bracket / a management command).

The adapter computes the dynamic field and persists entries only when explicitly requested.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Q

from api.models import Game
from accounts.models import Pick, PlayerIdentity, PlayoffSettings, PlayoffEntry, Challenge
from accounts.standings import compute_standings
from accounts.challenges import records as challenge_records
from accounts.confidence import confidence_points_for_user
from accounts.playoff_cuts import tiebreak_draw

from accounts.playoff_qualification import (
    PlayerRecord,
    QualificationResult,
    qualify_players,
    playoff_field_size,
    season_score,
    DEFAULT_K,
)

# Re-export the constant for callers that still import from the adapter
REGULAR_SEASON_WEEKS = 18


def _first_pick_week(user_id: int, season: int) -> Optional[int]:
    row = (
        Pick.objects.filter(user_id=user_id, game__season=season)
        .order_by("game__week")
        .values_list("game__week", flat=True)
        .first()
    )
    return row


def _weeks_with_picks(user_id: int, season: int, through_week: int = 18) -> Tuple[int, int]:
    """Return (total distinct weeks, recent weeks in the last 3)."""
    weeks = set(
        Pick.objects.filter(
            user_id=user_id,
            game__season=season,
            game__week__lte=through_week,
        ).values_list("game__week", flat=True)
    )
    recent_window = {through_week, through_week - 1, through_week - 2} & weeks
    return len(weeks), len(recent_window)


def _available_games(first_week: Optional[int], season: int) -> int:
    if first_week is None or first_week > REGULAR_SEASON_WEEKS:
        return 0
    return Game.objects.filter(
        season=season,
        week__gte=first_week,
        week__lte=REGULAR_SEASON_WEEKS,
    ).count()


def build_player_records(
    season: int,
    users: Optional[Sequence[User]] = None,
    through_week: int = REGULAR_SEASON_WEEKS,
) -> List[PlayerRecord]:
    """
    Materialise PlayerRecord objects from the live database.

    Call this after Week 9 (for the N snapshot) or after Week 18
    (for final membership).
    """
    if users is None:
        users = list(User.objects.filter(is_superuser=False))
    user_ids = [u.id for u in users]

    # Standings (wins/losses/ties) up to through_week
    standings = {
        s.user.id: s
        for s in compute_standings(
            season=season, users=users, through_week=through_week
        )
    }

    # Division membership
    identities = {
        pi.user_id: pi
        for pi in PlayerIdentity.objects.filter(
            user_id__in=user_ids, division_season=season
        )
    }

    # Confidence points (already implemented)
    conf_cache: Dict[int, float] = {}
    for uid in user_ids:
        conf_cache[uid] = confidence_points_for_user(
            User(id=uid), season=season
        ).get("points", 0) or 0

    # Finished challenge records and the number of distinct opponents.
    h2h = challenge_records(user_ids=user_ids, season=season)
    challenge_opponents: Dict[int, set] = defaultdict(set)
    for challenger_id, opponent_id in Challenge.objects.filter(
        season=season, status=Challenge.ACCEPTED
    ).filter(
        # Only challenges involving users in this qualification pool.
        # Both sides are considered for each participant.
        Q(challenger_id__in=user_ids) | Q(opponent_id__in=user_ids)
    ).values_list('challenger_id', 'opponent_id'):
        if challenger_id in user_ids:
            challenge_opponents[challenger_id].add(opponent_id)
        if opponent_id in user_ids:
            challenge_opponents[opponent_id].add(challenger_id)

    records: List[PlayerRecord] = []
    for u in users:
        st = standings.get(u.id)
        if st is None:
            continue
        ident = identities.get(u.id)
        first_week = _first_pick_week(u.id, season)
        weeks_total, weeks_recent = _weeks_with_picks(u.id, season, through_week)
        avail = _available_games(first_week, season)

        won, lost, tied = h2h.get(u.id, (0, 0, 0))
        # Simple credit: full wins, half ties.  (Full opponent-eligibility
        # filtering can be added later via apply_h2h_results.)
        credit = won + 0.5 * tied
        games = won + lost + tied

        records.append(
            PlayerRecord(
                user_id=u.id,
                username=u.username,
                division=ident.division if ident else "",
                wins=st.wins,
                losses=st.losses,
                ties=st.ties,
                available_games=avail,
                first_pick_week=first_week,
                weeks_with_picks=weeks_total,
                recent_weeks_with_picks=weeks_recent,
                confidence_points=conf_cache.get(u.id, 0),
                h2h_credit=credit,
                h2h_games=games,
                h2h_distinct_opponents=len(challenge_opponents.get(u.id, set())),
            )
        )
    return records


def run_qualification(
    season: int,
    *,
    k: int = DEFAULT_K,
    lambda_mult: float = 1.0,
    snapshot_n: Optional[int] = None,
    through_week: int = REGULAR_SEASON_WEEKS,
    write_entries: bool = False,
) -> QualificationResult:
    """
    High-level entry point.

    - snapshot_n: if the Week-9 active count was already frozen, pass it here
      so E is stable even if players keep joining.
    - write_entries: when True, create/update PlayoffEntry rows (final lock).
      Leave False for shadow mode.
    """
    players = build_player_records(season, through_week=through_week)

    # Sealed draws already used by the cut ladder
    draws = {
        p.user_id: tiebreak_draw(season, p.user_id) for p in players
    }

    result = qualify_players(
        players,
        k=k,
        lambda_mult=lambda_mult,
        force_N=snapshot_n,
        sealed_draws=draws,
    )

    if write_entries:
        _persist_entries(season, result)

    return result


def _persist_entries(season: int, result: QualificationResult) -> None:
    """Write the frozen PlayoffEntry rows (membership lock)."""
    # Clear any previous provisional entries for the season
    PlayoffEntry.objects.filter(season=season).delete()

    bulk = []
    for p in result.qualified:
        bulk.append(
            PlayoffEntry(
                user_id=p.user_id,
                season=season,
                route=p.qualification_route,
                division=p.division,
                regular_win_pct=(
                    (p.wins + 0.5 * p.ties) / (p.wins + p.losses + p.ties)
                    if (p.wins + p.losses + p.ties)
                    else 0.0
                ),
                head_to_head_wins=int(p.h2h_credit),  # approximate
                tiebreak_draw=tiebreak_draw(season, p.user_id),
                status=PlayoffEntry.ACTIVE,
            )
        )
    PlayoffEntry.objects.bulk_create(bulk)



# ---------------------------------------------------------------------------
# Suggested PlayoffSettings extensions (add via migration when ready)
# ---------------------------------------------------------------------------
"""
# accounts/models.py  – add to PlayoffSettings

difficulty_lambda = models.FloatField(
    default=1.0,
    help_text="Season difficulty multiplier applied to E(N). Keep in [0.8, 1.25]."
)
snapshot_week = models.PositiveSmallIntegerField(
    default=9,
    help_text="Week after which N, E and the seat map are frozen."
)
k_pseudo_picks = models.PositiveSmallIntegerField(
    default=250,
    help_text="Shrinkage constant for Season Score. Re-estimate each season."
)
use_dynamic_qualification = models.BooleanField(
    default=False,
    help_text="When True, championship_bracket uses the new capacity algorithm."
)
"""
