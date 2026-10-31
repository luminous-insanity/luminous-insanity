"""
Dynamic Playoff Qualification for GameDayPicks
================================================

Pure-Python implementation of the capacity-aware, Season-Score-based
qualification algorithm.  No Django dependency so it can be unit-tested
and reviewed in isolation.

Public API
----------
- playoff_field_size(active_n, lambda_mult=1.0) -> int
- season_score(...) -> float
- allocate_seats(E, n_active) -> (D, W, H)
- sainte_lague_seats(division_counts, total_seats) -> dict[str, int]
- challenge_score(...) -> float
- qualify_players(...) -> QualificationResult
- eligibility filters and the full tie-break key

Constants that are policy (not derived) are named and documented so they
can be recalibrated after real seasons.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Policy / derived constants
# ---------------------------------------------------------------------------

# Shrinkage pseudo-picks.  Chosen by split-half prediction on simulated data;
# re-estimate every season on real graded picks (odd weeks → even weeks).
DEFAULT_K = 250

# Minimum graded picks = k/2.  At this point the data already carries
# one-third of the weight in Season Score.
MIN_GRADED_PICKS_FACTOR = 0.5

# Completion rate required from a player's first-pick week through Week 18.
MIN_COMPLETION = 0.80

# Active-competitor definition used for the Week-9 snapshot of N.
MIN_WEEKS_PLAYED = 4
RECENT_WEEKS_WINDOW = 3
MIN_RECENT_WEEKS_WITH_PICKS = 2

# Capacity formula constants (all derived – see design document §4.3).
HALF_FIELD = 0.5
N_H = 100.0          # population where half-field exactly fills Super Bowl 50
EXPONENT = 0.5
FLOOR_PCT = 0.01     # 1 % quality floor
MIN_FIELD = 2

# Seat split (policy).  H is kept small because challenge evidence is thin.
DIVISION_SHARE = 0.60
AT_LARGE_SHARE = 0.30
H2H_SHARE = 0.10

# Below this size divisions become too thin for proportional seats.
TINY_LEAGUE_ACTIVE = 32
TINY_LEAGUE_E = 10

# H2H path gates.
H2H_MIN_OPPONENTS = 6
H2H_MAX_PER_OPPONENT = 2
H2H_PRIOR_WINS = 5
H2H_PRIOR_GAMES = 10
H2H_TOP_MULTIPLE = 2          # must be inside top (2·E) by Season Score


# ---------------------------------------------------------------------------
# Capacity
# ---------------------------------------------------------------------------

def playoff_field_size(active_n: int, lambda_mult: float = 1.0) -> int:
    """
    E(N) – continuous, bounded-scaling field size.

    E = max( ceil(0.01·N) , round( 0.5·N / (1 + √(N/100)) ) )
    then multiplied by the season difficulty knob λ and floored at 2.
    """
    if active_n < 2:
        return 0
    soft = HALF_FIELD * active_n / (1.0 + math.sqrt(active_n / N_H))
    e = max(math.ceil(FLOOR_PCT * active_n), round(soft))
    e = max(MIN_FIELD, round(e * max(0.0, lambda_mult)))
    return int(e)


def lookup_table(max_n: int = 500_000, step: int = 50) -> List[Tuple[int, int]]:
    """Pre-season lookup of E for every plausible N (publish this)."""
    rows = []
    n = 0
    while n <= max_n:
        rows.append((n, playoff_field_size(n)))
        n = n + step if n >= 100 else n + 10
    return rows


# ---------------------------------------------------------------------------
# Season Score
# ---------------------------------------------------------------------------

def season_score(
    wins: int,
    losses: int,
    ties: int,
    available_games: int,
    league_mu: float,
    k: int = DEFAULT_K,
) -> float:
    """
    One number used for every ranking decision.

    S = (W + ½·U + k·μ) / (A + k)

    - Skipped games score as coin flips (neutralises selective picking).
    - Shrinkage pulls small samples toward the league mean.
    - Late joiners are competitive once they have enough graded picks.
    """
    if available_games <= 0:
        return 0.0
    n = wins + losses + ties
    u = max(0, available_games - n)
    w = wins + 0.5 * ties
    return (w + 0.5 * u + k * league_mu) / (available_games + k)


def min_graded_picks(k: int = DEFAULT_K) -> int:
    return max(1, int(k * MIN_GRADED_PICKS_FACTOR))


# ---------------------------------------------------------------------------
# Eligibility & activity
# ---------------------------------------------------------------------------

@dataclass
class PlayerRecord:
    """Minimal facts needed for qualification.  Populate from your ORM."""
    user_id: int
    username: str = ""
    division: str = ""

    # Graded results (regular season only)
    wins: int = 0
    losses: int = 0
    ties: int = 0

    # Coverage
    available_games: int = 0          # A – games from first-pick week → 18
    first_pick_week: Optional[int] = None
    weeks_with_picks: int = 0         # distinct weeks that contain ≥1 pick
    recent_weeks_with_picks: int = 0  # of the last RECENT_WEEKS_WINDOW

    # Confidence (already collected in your system)
    confidence_points: float = 0.0    # sum of confidence on correct picks
    confidence_attempts: int = 0      # picks that carried a confidence value

    # Head-to-head (challenge) results – only eligible opponents count
    h2h_credit: float = 0.0           # 1 per win, 0.5 per tie, 0.5 vs below-median
    h2h_games: int = 0                # m – counted results after caps
    h2h_distinct_opponents: int = 0

    # Pre-computed (filled by the pipeline)
    season_score: float = 0.0
    challenge_score: float = 0.0
    eligible: bool = False
    active: bool = False              # counts toward N at Week-9 snapshot

    # Output
    qualification_route: str = ""
    seed: Optional[int] = None


def is_active(p: PlayerRecord) -> bool:
    """Week-9 snapshot definition of an active competitor."""
    return (
        p.weeks_with_picks >= MIN_WEEKS_PLAYED
        and p.available_games > 0
        and (p.wins + p.losses + p.ties) / p.available_games >= MIN_COMPLETION
        and p.recent_weeks_with_picks >= MIN_RECENT_WEEKS_WITH_PICKS
    )


def is_eligible(p: PlayerRecord, k: int = DEFAULT_K, median_s: float = 0.0) -> bool:
    """Final eligibility checked after Week 18."""
    graded = p.wins + p.losses + p.ties
    if graded < min_graded_picks(k):
        return False
    if p.available_games <= 0:
        return False
    if graded / p.available_games < MIN_COMPLETION:
        return False
    # Merit floor: must be at least as good as the typical regular.
    if p.season_score < median_s:
        return False
    return True


# ---------------------------------------------------------------------------
# Seat allocation
# ---------------------------------------------------------------------------

def allocate_seats(E: int, n_active: int) -> Tuple[int, int, int]:
    """Return (division_seats, at_large_seats, h2h_seats)."""
    if n_active < TINY_LEAGUE_ACTIVE or E < TINY_LEAGUE_E:
        return 0, E, 0
    H = int(E * H2H_SHARE)
    W = int(E * AT_LARGE_SHARE)
    D = E - H - W
    return D, W, H


def sainte_lague_seats(
    division_counts: Mapping[str, int],
    total_seats: int,
) -> Dict[str, int]:
    """
    Proportional allocation with no artificial minimum.
    A division that is too small simply receives zero seats; its players
    still compete for at-large and H2H spots.
    """
    if total_seats <= 0 or not division_counts:
        return {d: 0 for d in division_counts}

    # Standard Sainte-Laguë: successive quotients votes / (2·seats + 1)
    seats = {d: 0 for d in division_counts}
    for _ in range(total_seats):
        best_div = max(
            division_counts,
            key=lambda d: division_counts[d] / (2 * seats[d] + 1),
        )
        seats[best_div] += 1
    return seats


# ---------------------------------------------------------------------------
# Challenge (H2H) score
# ---------------------------------------------------------------------------

def challenge_score(
    credit: float,
    m: int,
    prior_wins: float = H2H_PRIOR_WINS,
    prior_games: float = H2H_PRIOR_GAMES,
) -> float:
    """
    C = (credit + prior_wins) / (m + prior_games)

    Prior of 5-in-10 prevents a handful of lucky results from carrying
    a ranking.  Credit already incorporates half-credit vs below-median
    opponents and the per-opponent cap.
    """
    return (credit + prior_wins) / (m + prior_games)


# ---------------------------------------------------------------------------
# Tie-break key (exactly E seats; never expand the field)
# ---------------------------------------------------------------------------

def qualification_key(p: PlayerRecord) -> Tuple:
    """
    Best-first sort key for every path.

    1. Season Score (higher better)
    2. Graded picks (more evidence better)
    3. Confidence points (already collected; rewards conviction)
    4. Sealed draw is applied later by the caller (stable, non-manipulable)
    """
    graded = p.wins + p.losses + p.ties
    return (
        -p.season_score,
        -graded,
        -p.confidence_points,
        p.username.lower(),
    )


def h2h_key(p: PlayerRecord) -> Tuple:
    """Ordering inside the H2H path only."""
    return (
        -p.challenge_score,
        -p.h2h_credit,
        -p.season_score,
        p.username.lower(),
    )


# ---------------------------------------------------------------------------
# Main qualification pipeline
# ---------------------------------------------------------------------------

@dataclass
class QualificationResult:
    E: int
    N: int
    division_seats: int
    at_large_seats: int
    h2h_seats: int
    seats_by_division: Dict[str, int]
    qualified: List[PlayerRecord]
    # Diagnostics
    division_filled: int = 0
    at_large_filled: int = 0
    h2h_filled: int = 0
    rolled_down: int = 0
    lapsed: int = 0
    median_s: float = 0.0
    league_mu: float = 0.0


def _median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    mid = len(s) // 2
    if len(s) % 2:
        return s[mid]
    return 0.5 * (s[mid - 1] + s[mid])


def qualify_players(
    players: Sequence[PlayerRecord],
    *,
    k: int = DEFAULT_K,
    lambda_mult: float = 1.0,
    force_E: Optional[int] = None,
    force_N: Optional[int] = None,
    sealed_draws: Optional[Mapping[int, int]] = None,
) -> QualificationResult:
    """
    Full pipeline.

    Parameters
    ----------
    players : list of PlayerRecord already populated with graded results,
              coverage, confidence and H2H credit.
    k, lambda_mult : season knobs.
    force_E / force_N : override for testing or when the Week-9 snapshot
                        has already been frozen.
    sealed_draws : optional {user_id: draw} for the final tie-break rung.
    """
    sealed_draws = sealed_draws or {}

    # 1. League mean win-rate on graded picks (only players with data)
    graded_players = [p for p in players if (p.wins + p.losses + p.ties) > 0]
    if graded_players:
        total_w = sum(p.wins + 0.5 * p.ties for p in graded_players)
        total_n = sum(p.wins + p.losses + p.ties for p in graded_players)
        league_mu = total_w / total_n
    else:
        league_mu = 0.5

    # 2. Season Score for everyone
    for p in players:
        p.season_score = season_score(
            p.wins, p.losses, p.ties, p.available_games, league_mu, k=k
        )
        p.challenge_score = challenge_score(p.h2h_credit, p.h2h_games)
        p.active = is_active(p)

    # 3. N and E
    N = force_N if force_N is not None else sum(1 for p in players if p.active)
    E = force_E if force_E is not None else playoff_field_size(N, lambda_mult)

    # 4. Eligibility (needs median of the eligible pool – iterative but cheap)
    # First pass: ignore merit floor to get a candidate pool, then apply floor.
    candidates = []
    for p in players:
        graded = p.wins + p.losses + p.ties
        if graded < min_graded_picks(k):
            p.eligible = False
            continue
        if p.available_games <= 0 or graded / p.available_games < MIN_COMPLETION:
            p.eligible = False
            continue
        candidates.append(p)

    median_s = _median([p.season_score for p in candidates]) if candidates else 0.0
    eligible = []
    for p in candidates:
        p.eligible = p.season_score >= median_s
        if p.eligible:
            eligible.append(p)

    # 5. Seat map
    D, W, H = allocate_seats(E, N)
    div_counts: Dict[str, int] = {}
    for p in players:
        if p.active and p.division:
            div_counts[p.division] = div_counts.get(p.division, 0) + 1
    seats_by_div = sainte_lague_seats(div_counts, D)

    # 6. Sort eligible players
    def full_key(p: PlayerRecord):
        base = qualification_key(p)
        draw = sealed_draws.get(p.user_id, 0)
        return base + (-draw,)          # higher draw wins (or invert if desired)

    eligible_sorted = sorted(eligible, key=full_key)

    qualified: List[PlayerRecord] = []
    taken = set()

    # 6a. Division seats
    division_filled = 0
    for div, n_seats in seats_by_div.items():
        if n_seats <= 0:
            continue
        div_players = [p for p in eligible_sorted if p.division == div and p.user_id not in taken]
        for p in div_players[:n_seats]:
            p.qualification_route = "Division qualifier"
            qualified.append(p)
            taken.add(p.user_id)
            division_filled += 1

    # 6b. At-large performance wildcards
    at_large_filled = 0
    remaining = [p for p in eligible_sorted if p.user_id not in taken]
    for p in remaining[:W]:
        p.qualification_route = "At-large wildcard"
        qualified.append(p)
        taken.add(p.user_id)
        at_large_filled += 1

    # 6c. Head-to-head wildcards (gated)
    h2h_filled = 0
    top_2e = set(p.user_id for p in eligible_sorted[: max(1, H2H_TOP_MULTIPLE * E)])
    h2h_pool = [
        p for p in eligible_sorted
        if p.user_id not in taken
        and p.user_id in top_2e
        and p.h2h_distinct_opponents >= H2H_MIN_OPPONENTS
    ]
    h2h_pool.sort(key=h2h_key)
    for p in h2h_pool[:H]:
        p.qualification_route = "Head-to-head wildcard"
        qualified.append(p)
        taken.add(p.user_id)
        h2h_filled += 1

    # 6d. Roll-down: any unfilled division or H2H seats become at-large
    still_needed = E - len(qualified)
    rolled = 0
    if still_needed > 0:
        cascade = [p for p in eligible_sorted if p.user_id not in taken]
        for p in cascade[:still_needed]:
            p.qualification_route = "At-large (roll-down)"
            qualified.append(p)
            taken.add(p.user_id)
            rolled += 1

    # Seats can lapse if the merit floor leaves too few eligible players.
    lapsed = max(0, E - len(qualified))

    # Assign provisional seeds (best Season Score first among qualifiers)
    qualified.sort(key=full_key)
    for i, p in enumerate(qualified, start=1):
        p.seed = i

    return QualificationResult(
        E=E,
        N=N,
        division_seats=D,
        at_large_seats=W,
        h2h_seats=H,
        seats_by_division=seats_by_div,
        qualified=qualified,
        division_filled=division_filled,
        at_large_filled=at_large_filled,
        h2h_filled=h2h_filled,
        rolled_down=rolled,
        lapsed=lapsed,
        median_s=median_s,
        league_mu=league_mu,
    )


# ---------------------------------------------------------------------------
# Convenience helpers for integration
# ---------------------------------------------------------------------------

def compute_available_games(
    first_pick_week: Optional[int],
    season_weeks: int = 18,
    games_per_week: Optional[Mapping[int, int]] = None,
) -> int:
    """
    A = total scheduled games from the player's first-pick week through Week 18.
    If games_per_week is omitted, assumes a constant 16-game week (NFL regular).
    """
    if first_pick_week is None or first_pick_week > season_weeks:
        return 0
    if games_per_week:
        return sum(
            games_per_week.get(w, 0)
            for w in range(first_pick_week, season_weeks + 1)
        )
    # Fallback: modern NFL has 17 games, but weeks vary; 16 is a safe average.
    return max(0, (season_weeks - first_pick_week + 1) * 16)


def apply_h2h_results(
    player: PlayerRecord,
    results: Sequence[Tuple[int, str, float]],
    *,
    opponent_is_eligible: Mapping[int, bool],
    opponent_s: Mapping[int, float],
    league_median_s: float,
) -> None:
    """
    Collapse raw challenge results into the capped credit / m used by C.

    results: iterable of (opponent_id, outcome, weight)
             outcome in {"win","loss","tie"}
    """
    from collections import defaultdict
    per_opp: Dict[int, List[float]] = defaultdict(list)

    for opp_id, outcome, weight in results:
        if not opponent_is_eligible.get(opp_id, False):
            continue
        if outcome == "win":
            credit = 1.0
            if opponent_s.get(opp_id, 0.5) < league_median_s:
                credit = 0.5
        elif outcome == "tie":
            credit = 0.5
        else:
            credit = 0.0
        per_opp[opp_id].append(credit * weight)

    # Cap at H2H_MAX_PER_OPPONENT results per opponent (best ones)
    total_credit = 0.0
    total_m = 0
    for opp_id, credits in per_opp.items():
        credits.sort(reverse=True)
        kept = credits[:H2H_MAX_PER_OPPONENT]
        total_credit += sum(kept)
        total_m += len(kept)

    player.h2h_credit = total_credit
    player.h2h_games = total_m
    player.h2h_distinct_opponents = len(per_opp)
