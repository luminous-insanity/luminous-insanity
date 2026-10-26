# Pure-Python tests for the ranking rules (no database needed).
#   python manage.py test accounts.test_ranking
from types import SimpleNamespace as Row
from unittest import TestCase

from accounts.ranking import (
    assign_ranks, format_pct, movement, record_gap, win_pct,
)


def row(w, l, t=0):
    return Row(wins=w, losses=l, ties=t, rank=0)


class RankingRuleTests(TestCase):
    def test_tied_players_share_a_rank_and_the_next_is_skipped(self):
        rows = assign_ranks([row(5, 1), row(5, 1), row(4, 2), row(3, 3)])
        self.assertEqual([r.rank for r in rows], [1, 1, 3, 4])

    def test_fewer_losses_beats_the_same_wins(self):
        rows = assign_ranks([row(4, 1), row(4, 2)])
        self.assertEqual([r.rank for r in rows], [1, 2])

    def test_most_ties_is_the_third_tiebreaker(self):
        rows = assign_ranks([row(4, 1, 1), row(4, 1, 0)])
        self.assertEqual([r.rank for r in rows], [1, 2])

    def test_win_percentage_counts_a_tie_as_half_a_win(self):
        self.assertAlmostEqual(win_pct(5, 3, 2), 60.0)
        self.assertEqual(format_pct(win_pct(7, 3, 0)), "70.0%")

    def test_no_percentage_without_completed_games(self):
        self.assertIsNone(win_pct(0, 0, 0))
        self.assertEqual(format_pct(None), "—")

    def test_percentage_never_changes_rank(self):
        # 3-0 is 100% and 5-3 is 62.5%, but 5 wins still ranks higher.
        rows = assign_ranks([row(5, 3), row(3, 0)])
        self.assertEqual([r.rank for r in rows], [1, 2])

    def test_rank_movement_labels(self):
        self.assertEqual(movement(1, 4, 3), ("up", "↑3"))
        self.assertEqual(movement(5, 3, 3), ("down", "↓2"))
        self.assertEqual(movement(2, 2, 3), ("same", "—0"))
        self.assertEqual(movement(2, None, 3), ("new", "New"))
        self.assertEqual(movement(2, None, 1), ("none", "—"))

    def test_season_gap_wording(self):
        self.assertEqual(record_gap((5, 2, 0), (3, 4, 0))[1], "You lead by 2 wins")
        self.assertEqual(record_gap((3, 4, 0), (4, 3, 0))[1], "You trail by 1 win")
        self.assertEqual(record_gap((4, 2, 0), (4, 2, 0))[0], "tied")
