"""
Integrity scenarios: late joiners, score corrections, ties, season finalization,
and repeated sync safety.

Run:  python manage.py test accounts.test_integrity
"""
from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import Pick
from accounts.ranking import assign_ranks, rank_key, win_pct
from accounts.standings import compute_standings, standing_for
from accounts.leaderboard import season_is_finalized, week_is_complete
from api.helpers_for_tests import FakeApi, make_final, make_game, raw_game, raw_score
from api.models import Game
from api.rules import grade_pick
from api.services import run_sync, sync_scores

SETTINGS = dict(NFL_SEASON=2026)


def make_user(name):
    return User.objects.create_user(name, f"{name}@example.com", "pw-12345-xyz")


@override_settings(**SETTINGS)
class LateJoinerStandingsTests(TestCase):
    """A player who only picks a few games must not dominate pure win-pct rankings
    in ways that disagree with volume-aware playoff eligibility."""

    def test_late_joiner_perfect_record_has_fewer_wins_than_full_season_player(self):
        full = make_user("full")
        late = make_user("late")
        # 10 home-win finals for the full-season player
        games = [make_final(make_game(week=w), 21, 10) for w in range(1, 11)]
        for g in games:
            Pick.objects.create(user=full, game=g, team_picked="home")
        # Late joiner only plays week 10, wins
        Pick.objects.create(user=late, game=games[-1], team_picked="home")

        standings = {s.user.username: s for s in compute_standings(season=2026)}
        self.assertEqual(standings["full"].wins, 10)
        self.assertEqual(standings["late"].wins, 1)
        # Rank order: more wins first
        order = [s.user.username for s in compute_standings(season=2026)]
        self.assertEqual(order[0], "full")
        self.assertGreater(order.index("late"), 0)

    def test_grade_pick_none_when_scores_missing(self):
        self.assertIsNone(grade_pick("home", None, 10))
        self.assertIsNone(grade_pick("home", 10, None))
        self.assertEqual(grade_pick("home", 10, 10), "tie")
        self.assertEqual(grade_pick("home", 14, 10), "win")
        self.assertEqual(grade_pick("away", 14, 10), "loss")


@override_settings(**SETTINGS)
class ScoreCorrectionTests(TestCase):
    """Changing a final score must change standings; re-sync must not double-count."""

    def test_correcting_final_score_updates_standings(self):
        alice = make_user("alice")
        game = make_final(make_game(), 27, 20)  # home wins
        Pick.objects.create(user=alice, game=game, team_picked="home")
        self.assertEqual(standing_for(alice, season=2026).wins, 1)

        # Official score correction: away actually won
        game.home_score = 17
        game.away_score = 24
        game.save()
        self.assertEqual(standing_for(alice, season=2026).wins, 0)
        self.assertEqual(standing_for(alice, season=2026).losses, 1)

    def test_regrading_does_not_accumulate(self):
        bob = make_user("bob")
        game = make_final(make_game(), 10, 3)
        Pick.objects.create(user=bob, game=game, team_picked="home")
        for _ in range(5):
            s = standing_for(bob, season=2026)
            self.assertEqual((s.wins, s.losses, s.ties), (1, 0, 0))


@override_settings(**SETTINGS)
class TiesAndRankingTests(TestCase):
    def test_tie_game_counts_as_tie_for_both_sides(self):
        a, b = make_user("a"), make_user("b")
        game = make_final(make_game(), 20, 20)
        Pick.objects.create(user=a, game=game, team_picked="home")
        Pick.objects.create(user=b, game=game, team_picked="away")
        sa, sb = standing_for(a, season=2026), standing_for(b, season=2026)
        self.assertEqual((sa.wins, sa.losses, sa.ties), (0, 0, 1))
        self.assertEqual((sb.wins, sb.losses, sb.ties), (0, 0, 1))

    def test_shared_rank_on_identical_records(self):
        users = [make_user(n) for n in ("alice", "bob", "carol")]
        game = make_final(make_game(), 14, 7)
        for u in users[:2]:
            Pick.objects.create(user=u, game=game, team_picked="home")
        # carol loses
        Pick.objects.create(user=users[2], game=game, team_picked="away")
        rows = list(compute_standings(season=2026))
        ranked = assign_ranks(rows)
        # alice and bob both rank 1; carol is 3
        by_name = {r.user.username: r.rank for r in ranked}
        self.assertEqual(by_name["alice"], 1)
        self.assertEqual(by_name["bob"], 1)
        self.assertEqual(by_name["carol"], 3)


@override_settings(**SETTINGS)
class SeasonFinalizationTests(TestCase):
    def test_not_finalized_without_all_18_weeks(self):
        for w in range(1, 10):
            make_final(make_game(week=w, season=2026), 10, 3)
        self.assertFalse(season_is_finalized(2026))

    def test_not_finalized_if_any_game_not_final(self):
        for w in range(1, 19):
            make_final(make_game(week=w, season=2026, game_id=f"F{w}"), 10, 3)
        make_game(week=5, season=2026, game_id="OPEN5")  # scheduled leftover
        self.assertFalse(season_is_finalized(2026))

    def test_finalized_when_all_18_weeks_complete(self):
        for w in range(1, 19):
            make_final(make_game(week=w, season=2026, game_id=f"S{w}"), 21, 14)
        self.assertTrue(season_is_finalized(2026))

    def test_week_is_complete(self):
        make_final(make_game(week=3, season=2026, game_id="w3a"), 10, 7)
        make_final(make_game(week=3, season=2026, game_id="w3b"), 14, 10)
        self.assertTrue(week_is_complete(2026, 3))
        make_game(week=3, season=2026, game_id="w3c")  # not final
        self.assertFalse(week_is_complete(2026, 3))


@override_settings(**SETTINGS)
class RepeatedSyncTests(TestCase):
    """Running sync twice must not create duplicate games or corrupt scores."""

    def test_schedule_sync_is_idempotent(self):
        kickoff = timezone.now() + timedelta(days=1)
        raw = raw_game("IDEM001_BAL@KC", "KC", "BAL", kickoff=kickoff)
        fake = FakeApi(schedules={1: [raw]}, scores={1: {}})
        with patch("api.services._get", fake):
            from api.services import sync_schedule
            a, _ = sync_schedule(1)
            b, _ = sync_schedule(1)
        self.assertEqual(Game.objects.filter(game_id="IDEM001_BAL@KC").count(), 1)
        self.assertEqual(a, 1)
        self.assertEqual(b, 1)

    def test_score_sync_updates_without_duplicating(self):
        game = make_game(game_id="SCORE001_BAL@KC", week=1)
        game.kickoff = timezone.now() - timedelta(hours=3)
        game.save()
        fake = FakeApi(
            schedules={},
            scores={1: {"SCORE001_BAL@KC": raw_score(2, 24, 17)}},
        )
        with patch("api.services._get", fake):
            n1 = sync_scores(1)
            n2 = sync_scores(1)
        game.refresh_from_db()
        self.assertEqual(game.status, Game.FINAL)
        self.assertEqual(game.home_score, 24)
        self.assertEqual(game.away_score, 17)
        self.assertEqual(Game.objects.filter(game_id="SCORE001_BAL@KC").count(), 1)
