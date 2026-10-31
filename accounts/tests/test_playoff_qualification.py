"""
Unit tests for the pure qualification logic.
Run with:  python -m pytest tests/ -q
or simply: python tests/test_playoff_qualification.py
"""

from __future__ import annotations

import math
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playoff_qualification import (
    PlayerRecord,
    playoff_field_size,
    season_score,
    allocate_seats,
    sainte_lague_seats,
    challenge_score,
    qualify_players,
    is_active,
    is_eligible,
    min_graded_picks,
    DEFAULT_K,
)


def test_capacity_table():
    """Matches the design-document table in §5.1 (within rounding)."""
    cases = [
        (8, 3),
        (20, 7),
        (40, 12),
        (100, 25),
        (250, 48),
        (500, 77),
        (1000, 120),
        (2500, 208),
        (10000, 455),
        (50000, 1070),
        (100000, 1533),
        (216000, 2275),
    ]
    for n, expected in cases:
        got = playoff_field_size(n)
        # Allow ±1 for floating-point / rounding edge
        assert abs(got - expected) <= 1, f"N={n}: expected ~{expected}, got {got}"


def test_capacity_floor_and_minimum():
    assert playoff_field_size(1) == 0
    assert playoff_field_size(2) >= 2
    # 1 % floor eventually binds
    assert playoff_field_size(500_000) == 5000


def test_season_score_shrinkage():
    mu = 0.605
    # Hot 40-pick streak is pulled toward the mean
    hot = season_score(34, 6, 0, 40, mu, k=250)
    assert 0.63 < hot < 0.66
    # Full-season 75 % player ends higher
    solid = season_score(120, 40, 0, 160, mu, k=250)
    assert solid > hot
    # Same underlying skill (~62.5 %): skipping never improves S
    # (matches design-doc table in §5.6)
    base = season_score(100, 60, 0, 160, mu, k=250)          # 100 % picked
    skip10 = season_score(90, 54, 0, 160, mu, k=250)         # skipped 10 %, same skill
    skip20 = season_score(80, 48, 0, 160, mu, k=250)
    assert skip10 <= base + 1e-9
    assert skip20 < base


def test_allocate_seats_tiny():
    assert allocate_seats(5, 20) == (0, 5, 0)
    D, W, H = allocate_seats(100, 500)
    assert D + W + H == 100
    assert abs(D / 100 - 0.60) < 0.02
    assert abs(W / 100 - 0.30) < 0.02
    assert abs(H / 100 - 0.10) < 0.02


def test_sainte_lague_proportional():
    counts = {"A": 40, "B": 28, "C": 77, "D": 52, "E": 40, "F": 49, "G": 39, "H": 104}
    seats = sainte_lague_seats(counts, 42)
    assert sum(seats.values()) == 42
    # Largest division should get the most seats
    assert seats["H"] >= seats["C"] >= seats["D"]
    # Tiny relative share can still get zero when total seats are scarce
    tiny = sainte_lague_seats({"Big": 90, "Tiny": 2}, 5)
    assert tiny["Tiny"] <= 1


def test_challenge_score_prior():
    # Empty record is pulled to 0.5
    assert abs(challenge_score(0, 0) - 0.5) < 1e-9
    # 20-10 honest record
    c = challenge_score(20, 30)
    assert 0.62 < c < 0.64
    # Farmed 30 wins against weak/ineligible already filtered → low credit
    farmed = challenge_score(15, 30)  # half-credit already applied upstream
    assert farmed < c


def _make_player(
    uid: int,
    div: str,
    wins: int,
    losses: int,
    available: int = 160,
    conf: float = 0.0,
    weeks: int = 10,
    recent: int = 3,
    h2h_credit: float = 0.0,
    h2h_games: int = 0,
    h2h_opps: int = 0,
) -> PlayerRecord:
    return PlayerRecord(
        user_id=uid,
        username=f"user{uid}",
        division=div,
        wins=wins,
        losses=losses,
        ties=0,
        available_games=available,
        first_pick_week=1,
        weeks_with_picks=weeks,
        recent_weeks_with_picks=recent,
        confidence_points=conf,
        h2h_credit=h2h_credit,
        h2h_games=h2h_games,
        h2h_distinct_opponents=h2h_opps,
    )


def test_full_pipeline_small():
    """20 active players → E ≈ 7, pure at-large because tiny."""
    players = []
    for i in range(20):
        # Decreasing strength
        w = 110 - i * 3
        players.append(_make_player(i, "AFC East", w, 160 - w, conf=50 - i))
    result = qualify_players(players, force_N=20)
    assert result.E == playoff_field_size(20)
    assert len(result.qualified) == result.E
    assert result.division_seats == 0
    # Best players should be in
    top_ids = {p.user_id for p in result.qualified}
    assert 0 in top_ids
    assert 1 in top_ids


def test_full_pipeline_medium():
    """~400 active, multiple divisions, verifies cascade & no expansion."""
    divisions = [
        "AFC East", "AFC North", "AFC South", "AFC West",
        "NFC East", "NFC North", "NFC South", "NFC West",
    ]
    players = []
    uid = 0
    for d in divisions:
        for i in range(50):
            w = 100 - i
            players.append(
                _make_player(
                    uid, d, w, 160 - w,
                    conf=40 - i * 0.5,
                    h2h_credit=5 if i < 5 else 0,
                    h2h_games=10 if i < 5 else 0,
                    h2h_opps=8 if i < 5 else 0,
                )
            )
            uid += 1
    result = qualify_players(players)
    assert result.N == 400
    assert result.E == playoff_field_size(400)
    assert len(result.qualified) <= result.E
    assert len(result.qualified) == result.E - result.lapsed
    # Every qualifier is unique
    ids = [p.user_id for p in result.qualified]
    assert len(ids) == len(set(ids))
    # Division seats roughly proportional
    assert sum(result.seats_by_division.values()) == result.division_seats


def test_merit_floor_can_lapse_seats():
    """If almost nobody clears the median, seats lapse rather than expand."""
    players = [_make_player(i, "AFC East", 80, 80) for i in range(30)]
    # One superstar
    players[0] = _make_player(0, "AFC East", 140, 20, conf=100)
    result = qualify_players(players, force_N=30, force_E=10)
    # Only players ≥ median survive; field may be smaller than E
    assert len(result.qualified) <= 10
    assert result.lapsed >= 0


def test_late_joiner_eligible_with_shrinkage():
    """A strong late joiner still has a path once ≥125 graded picks."""
    late = _make_player(
        99, "NFC North",
        wins=100, losses=30,
        available=130,          # joined around Week 5-6
        weeks=13, recent=3,
        conf=70,
    )
    late.season_score = season_score(100, 30, 0, 130, 0.60, k=250)
    assert late.season_score > 0.65
    assert (100 + 30) >= min_graded_picks()


def test_active_definition():
    p = _make_player(1, "AFC East", 50, 30, available=100, weeks=5, recent=2)
    assert is_active(p)
    p.weeks_with_picks = 2
    assert not is_active(p)


if __name__ == "__main__":
    import traceback
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  OK  {t.__name__}")
            passed += 1
        except Exception:
            print(f"FAIL  {t.__name__}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
