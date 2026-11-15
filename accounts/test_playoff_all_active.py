"""Tests for the small-league rule (pure Python; no database needed)."""
import unittest

from accounts.playoff_all_active import ROUTE_LABEL, apply_all_active_rule
from accounts.playoff_cuts import cut_targets
from accounts.playoff_qualification import PlayerRecord, qualify_players


def _league(n, active_count=None):
    """n players; the first `active_count` are active, ranked by wins."""
    active_count = n if active_count is None else active_count
    players = []
    for i in range(n):
        is_act = i < active_count
        players.append(PlayerRecord(
            user_id=i + 1, username=f'p{i + 1}',
            wins=(120 - i) if is_act else 1, losses=(60 + i) if is_act else 1,
            available_games=(180 if is_act else 2),
            first_pick_week=1, weeks_with_picks=(18 if is_act else 1),
            recent_weeks_with_picks=(3 if is_act else 0),
        ))
    return players


class AllActiveRuleTests(unittest.TestCase):
    def test_everyone_active_qualifies_at_or_below_threshold(self):
        for n in (5, 20, 49, 50):
            players = _league(n)
            result = qualify_players(players)
            before = len(result.qualified)
            result = apply_all_active_rule(result, players, 50)
            self.assertEqual(len(result.qualified), n, n)
            self.assertEqual(result.E, n)
            self.assertEqual({p.user_id for p in result.qualified}, {p.user_id for p in players})
            self.assertTrue(all(p.qualification_route == ROUTE_LABEL for p in result.qualified))
            self.assertEqual([p.seed for p in result.qualified], list(range(1, n + 1)))
            if n >= 20:
                self.assertLess(before, n)  # the plain algorithm would have cut people

    def test_inactive_players_do_not_qualify(self):
        players = _league(30, active_count=20)
        result = apply_all_active_rule(qualify_players(players), players, 50)
        self.assertEqual({p.user_id for p in result.qualified}, set(range(1, 21)))

    def test_above_threshold_is_untouched(self):
        players = _league(120)
        result = qualify_players(players)
        qualified_before = [p.user_id for p in result.qualified]
        E_before = result.E
        result = apply_all_active_rule(result, players, 50)
        self.assertEqual([p.user_id for p in result.qualified], qualified_before)
        self.assertEqual(result.E, E_before)

    def test_threshold_zero_turns_rule_off(self):
        players = _league(30)
        result = qualify_players(players)
        before = [p.user_id for p in result.qualified]
        result = apply_all_active_rule(result, players, 0)
        self.assertEqual([p.user_id for p in result.qualified], before)

    def test_no_cuts_when_field_is_50_or_fewer(self):
        for n in (1, 10, 50):
            self.assertEqual(cut_targets(n, 50, 3), [n, n, n])


if __name__ == '__main__':
    unittest.main()
