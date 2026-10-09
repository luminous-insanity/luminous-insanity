# api/tests.py
#
# Run everything with:   python manage.py test
# Run only this file:    python manage.py test api
#
# No test here calls the real API; see helpers_for_tests.FakeApi.
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import Pick
from api import services
from api.helpers_for_tests import (
    FakeApi, hours_from_now, make_final, make_game, raw_game, raw_score,
)
from api.models import Game

SETTINGS = dict(
    NFL_SEASON=2026,
    NFL_API_KEY="test-key",
    NFL_API_HOST="api.example.test",
    SYNC_TOKEN="secret-token",
)


def ago(hours):
    return timezone.now() - timedelta(hours=hours)


# ------------------------------------------------------------------ models --

@override_settings(**SETTINGS)
class GameModelTests(TestCase):
    def test_home_team_wins(self):
        game = make_final(make_game(), 27, 20)
        self.assertTrue(game.is_final)
        self.assertEqual(game.winner_side, "home")
        self.assertEqual(game.winner_name, "KC")

    def test_away_team_wins(self):
        game = make_final(make_game(), 3, 24)
        self.assertEqual(game.winner_side, "away")
        self.assertEqual(game.winner_name, "BAL")

    def test_tie(self):
        game = make_final(make_game(), 20, 20)
        self.assertEqual(game.winner_side, "tie")
        self.assertEqual(game.winner_name, "Draw")

    def test_no_winner_until_final(self):
        game = make_game()
        self.assertFalse(game.is_final)
        self.assertIsNone(game.winner_side)
        self.assertIsNone(game.winner_name)

    def test_final_status_without_scores_is_not_final(self):
        game = make_game(status=Game.FINAL)   # no scores saved
        self.assertFalse(game.is_final)

    def test_picks_lock_at_kickoff(self):
        self.assertFalse(make_game(kickoff=ago(-2)).has_started)   # 2 hours from now
        self.assertTrue(make_game(kickoff=ago(2)).has_started)     # 2 hours ago

    def test_lock_falls_back_to_game_day_when_no_kickoff_time(self):
        long_ago = make_game(kickoff=None, game_date=timezone.localdate() - timedelta(days=3))
        far_ahead = make_game(kickoff=None, game_date=timezone.localdate() + timedelta(days=3))
        self.assertTrue(long_ago.has_started)
        self.assertFalse(far_ahead.has_started)

    def test_game_id_must_be_unique(self):
        make_game(game_id="DUPLICATE")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_game(game_id="DUPLICATE")


class MigrationTests(TestCase):
    def test_models_and_migrations_match(self):
        """If this fails, a model changed without a migration. The same would
        break on PythonAnywhere when you run migrate."""
        try:
            call_command("makemigrations", "--check", "--dry-run", verbosity=0)
        except SystemExit:
            self.fail("Models have changes with no migration. Run: python manage.py makemigrations")


# ---------------------------------------------------------- schedule sync --

@override_settings(**SETTINGS)
class SyncScheduleTests(TestCase):
    def test_creates_games_with_kickoff_times(self):
        k = hours_from_now(48)
        fake = FakeApi(schedules={1: [
            raw_game("A_BAL@KC", "KC", "BAL", k),
            raw_game("B_DAL@NYG", "NYG", "DAL", k),
        ]})
        with patch("api.services._get", fake):
            seen, with_kickoff = services.sync_schedule(1)
        self.assertEqual((seen, with_kickoff), (2, 2))
        game = Game.objects.get(game_id="A_BAL@KC")
        self.assertEqual((game.season, game.week, game.home_team, game.away_team), (2026, 1, "KC", "BAL"))
        self.assertEqual(game.kickoff, k)

    def test_running_twice_does_not_duplicate_games(self):
        fake = FakeApi(schedules={1: [raw_game("A_BAL@KC", "KC", "BAL", hours_from_now(48))]})
        with patch("api.services._get", fake):
            services.sync_schedule(1)
            services.sync_schedule(1)
        self.assertEqual(Game.objects.count(), 1)

    def test_reloading_a_week_keeps_everyones_picks(self):
        """The old code deleted the week's games first, which deleted all picks."""
        user = User.objects.create_user("alice", password="pw")
        game = make_game(game_id="A_BAL@KC")
        Pick.objects.create(user=user, game=game, team_picked="home")
        fake = FakeApi(schedules={1: [raw_game("A_BAL@KC", "KC", "BAL", hours_from_now(48))]})
        with patch("api.services._get", fake):
            services.sync_schedule(1)
        self.assertEqual(Game.objects.count(), 1)
        self.assertEqual(Pick.objects.count(), 1)

    def test_flexed_kickoff_time_is_updated(self):
        first, second = hours_from_now(48), hours_from_now(30)
        with patch("api.services._get", FakeApi(schedules={1: [raw_game("A", "KC", "BAL", first)]})):
            services.sync_schedule(1)
        with patch("api.services._get", FakeApi(schedules={1: [raw_game("A", "KC", "BAL", second)]})):
            services.sync_schedule(1)
        self.assertEqual(Game.objects.get(game_id="A").kickoff, second)

    def test_known_kickoff_is_not_erased_by_a_missing_one(self):
        known = hours_from_now(48)
        with patch("api.services._get", FakeApi(schedules={1: [raw_game("A", "KC", "BAL", known)]})):
            services.sync_schedule(1)
        with patch("api.services._get", FakeApi(schedules={1: [raw_game("A", "KC", "BAL", None)]})):
            services.sync_schedule(1)
        self.assertEqual(Game.objects.get(game_id="A").kickoff, known)

    def test_unusable_entries_are_skipped(self):
        good = raw_game("A", "KC", "BAL", hours_from_now(48))
        bad = {**raw_game("B", "KC", "BAL", hours_from_now(48)), "home": None}
        with patch("api.services._get", FakeApi(schedules={1: [good, bad]})):
            seen, _ = services.sync_schedule(1)
        self.assertEqual(seen, 1)
        self.assertEqual(Game.objects.count(), 1)

    def test_schedule_sync_never_touches_scores(self):
        make_final(make_game(game_id="A"), 27, 20)
        with patch("api.services._get", FakeApi(schedules={1: [raw_game("A", "KC", "BAL", ago(5))]})):
            services.sync_schedule(1)
        game = Game.objects.get(game_id="A")
        self.assertEqual((game.status, game.home_score, game.away_score), (Game.FINAL, 27, 20))


# ------------------------------------------------------------- score sync --

@override_settings(**SETTINGS)
class SyncScoresTests(TestCase):
    def sync(self, week, payload):
        with patch("api.services._get", FakeApi(scores={week: payload})):
            return services.sync_scores(week)

    def test_final_game_is_saved(self):
        game = make_game(game_id="G1", kickoff=ago(5))
        count = self.sync(1, {"G1": raw_score(2, 27, 20)})
        game.refresh_from_db()
        self.assertEqual(count, 1)
        self.assertEqual((game.status, game.home_score, game.away_score), (Game.FINAL, 27, 20))
        self.assertIsNotNone(game.scores_checked_at)

    def test_game_in_progress_is_not_final(self):
        game = make_game(game_id="G1", kickoff=ago(1))
        count = self.sync(1, {"G1": raw_score(1, 10, 7)})
        game.refresh_from_db()
        self.assertEqual(count, 0)
        self.assertEqual(game.status, Game.LIVE)
        self.assertFalse(game.is_final)

    def test_final_without_both_scores_is_not_graded(self):
        game = make_game(game_id="G1", kickoff=ago(5))
        count = self.sync(1, {"G1": raw_score(2, None, None)})
        game.refresh_from_db()
        self.assertEqual(count, 0)
        self.assertFalse(game.is_final)

    def test_not_started_game_keeps_no_scores(self):
        game = make_game(game_id="G1")
        self.sync(1, {"G1": raw_score(0, None, None)})
        game.refresh_from_db()
        self.assertEqual(game.status, Game.SCHEDULED)
        self.assertIsNone(game.home_score)

    def test_unknown_game_in_response_is_ignored(self):
        self.sync(1, {"NOT_IN_OUR_DB": raw_score(2, 10, 3)})
        self.assertEqual(Game.objects.count(), 0)


# --------------------------------------------- deciding when to call the API --

@override_settings(**SETTINGS)
class GamesNeedingScoresTests(TestCase):
    def ids(self):
        return {g.game_id for g in services.games_needing_scores()}

    def test_game_that_has_not_started_is_skipped(self):
        make_game(game_id="G1", kickoff=ago(-3))
        self.assertEqual(self.ids(), set())

    def test_started_unchecked_game_is_included(self):
        make_game(game_id="G1", kickoff=ago(1))
        self.assertEqual(self.ids(), {"G1"})

    def test_final_game_is_skipped(self):
        make_final(make_game(game_id="G1", kickoff=ago(5)), 10, 3)
        self.assertEqual(self.ids(), set())

    def test_live_game_is_rechecked_every_ten_minutes(self):
        make_game(game_id="JUST_CHECKED", kickoff=ago(1), scores_checked_at=ago(5 / 60))
        make_game(game_id="DUE", kickoff=ago(1), scores_checked_at=ago(15 / 60))
        self.assertEqual(self.ids(), {"DUE"})

    def test_game_older_than_eight_hours_is_rechecked_daily(self):
        make_game(game_id="CHECKED_1H_AGO", kickoff=ago(12), scores_checked_at=ago(1))
        make_game(game_id="CHECKED_25H_AGO", kickoff=ago(12), scores_checked_at=ago(25))
        self.assertEqual(self.ids(), {"CHECKED_25H_AGO"})

    def test_a_run_that_caught_the_game_mid_play_is_followed_up(self):
        """With only a few runs a week, the next run must grade a game the last run saw live."""
        make_game(game_id="SAW_IT_MIDGAME", kickoff=ago(10), scores_checked_at=ago(6.5))    # looked 3.5h after kickoff
        make_game(game_id="LOOKED_AFTER_END", kickoff=ago(10), scores_checked_at=ago(1))   # looked 9h after kickoff
        self.assertEqual(self.ids(), {"SAW_IT_MIDGAME"})

    def test_very_old_unfinished_game_is_given_up_on(self):
        make_game(game_id="OLD", kickoff=ago(24 * 20), game_date=timezone.localdate() - timedelta(days=20))
        self.assertEqual(self.ids(), set())


@override_settings(**SETTINGS)
class CurrentWeekTests(TestCase):
    def test_week_1_before_anything_is_loaded(self):
        self.assertEqual(services.current_week(), 1)

    def test_first_week_with_an_unfinished_game(self):
        make_final(make_game(week=3, game_date=timezone.localdate() - timedelta(days=3)), 20, 10)
        make_game(week=4)
        self.assertEqual(services.current_week(), 4)

    def test_stays_on_last_week_when_everything_is_final(self):
        make_final(make_game(week=4, game_date=timezone.localdate() - timedelta(days=1)), 20, 10)
        self.assertEqual(services.current_week(), 4)

    def test_other_seasons_are_ignored(self):
        make_game(week=9, season=2024)
        self.assertEqual(services.current_week(), 1)


# ---------------------------------------------------------------- run_sync --

@override_settings(**SETTINGS)
class RunSyncTests(TestCase):
    def run_with(self, fake):
        with patch("api.services._get", fake):
            return services.run_sync()

    def test_first_run_loads_week_1(self):
        fake = FakeApi(schedules={1: [raw_game("G1", "KC", "BAL", hours_from_now(48))]})
        report = self.run_with(fake)
        self.assertEqual(report["schedule_weeks"], [1])
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["current_week"], 1)
        self.assertEqual(fake.calls, [("getNFLGamesForWeek", 1)])
        self.assertEqual(Game.objects.count(), 1)

    def test_no_api_calls_when_nothing_needs_doing(self):
        make_game(game_id="G1")   # kicks off tomorrow, schedule is fresh
        fake = FakeApi()
        self.run_with(fake)
        self.assertEqual(fake.calls, [])

    def test_grades_finished_games_and_opens_the_next_week(self):
        make_game(game_id="G1", kickoff=ago(5))
        make_game(game_id="G2", kickoff=ago(4))
        fake = FakeApi(
            scores={1: {"G1": raw_score(2, 27, 20), "G2": raw_score(2, 10, 13)}},
            schedules={2: [raw_game("G3", "NYG", "DAL", hours_from_now(24 * 5))]},
        )
        report = self.run_with(fake)
        self.assertEqual(Game.objects.filter(week=1, status=Game.FINAL).count(), 2)
        self.assertEqual(report["final_games"], 2)
        self.assertEqual(report["schedule_weeks"], [2])
        self.assertEqual(report["current_week"], 2)
        self.assertEqual(fake.calls, [("getNFLScoresOnly", 1), ("getNFLGamesForWeek", 2)])

    def test_running_it_twice_is_harmless(self):
        make_game(game_id="G1", kickoff=ago(5))
        fake = FakeApi(
            scores={1: {"G1": raw_score(2, 27, 20)}},
            schedules={2: [raw_game("G3", "NYG", "DAL", hours_from_now(24 * 5))]},
        )
        self.run_with(fake)
        calls_after_first = len(fake.calls)
        games_after_first = Game.objects.count()
        self.run_with(fake)
        self.assertEqual(len(fake.calls), calls_after_first)      # no more API calls
        self.assertEqual(Game.objects.count(), games_after_first)  # no duplicates
        self.assertEqual(Game.objects.get(game_id="G1").home_score, 27)

    def test_two_widely_spaced_runs_grade_a_late_game(self):
        """Thursday 11:45 PM run sees it live; the Friday morning run must finish the job."""
        make_game(game_id="TNF", kickoff=ago(10), scores_checked_at=ago(6.5), status=Game.LIVE)
        fake = FakeApi(
            scores={1: {"TNF": raw_score(2, 24, 20)}},
            schedules={2: [raw_game("NEXT", "NYG", "DAL", hours_from_now(24 * 5))]},
        )
        report = self.run_with(fake)
        game = Game.objects.get(game_id="TNF")
        self.assertEqual((game.status, game.home_score, game.away_score), (Game.FINAL, 24, 20))
        self.assertEqual(report["final_games"], 1)

    def test_api_failure_is_reported_not_raised(self):
        make_game(game_id="G1", kickoff=ago(5))
        report = self.run_with(FakeApi(error="boom"))
        self.assertEqual(len(report["errors"]), 1)
        self.assertEqual(Game.objects.get(game_id="G1").status, Game.SCHEDULED)

    def test_stale_schedule_is_refreshed_once_a_day(self):
        make_game(game_id="G1", kickoff=hours_from_now(48), schedule_synced_at=ago(30))
        new_kickoff = hours_from_now(30)
        fake = FakeApi(schedules={1: [raw_game("G1", "KC", "BAL", new_kickoff)]})
        report = self.run_with(fake)
        self.assertEqual(report["schedule_weeks"], [1])
        self.assertEqual(Game.objects.get(game_id="G1").kickoff, new_kickoff)

    def test_no_api_calls_after_the_regular_season_ends(self):
        make_final(make_game(week=18, game_date=timezone.localdate() - timedelta(days=1)), 20, 10)
        fake = FakeApi()
        self.run_with(fake)
        self.assertEqual(fake.calls, [])


# ----------------------------------------------------------- the sync URL --

@override_settings(**SETTINGS)
class SyncViewTests(TestCase):
    GOOD_REPORT = {"errors": [], "schedule_weeks": [], "score_weeks": [], "final_games": 0, "current_week": 4}

    def test_missing_or_wrong_token_is_forbidden(self):
        with patch("api.views.run_sync") as run:
            self.assertEqual(self.client.get("/api/sync/").status_code, 403)
            self.assertEqual(self.client.get("/api/sync/?token=nope").status_code, 403)
            run.assert_not_called()

    @override_settings(SYNC_TOKEN="")
    def test_an_empty_token_never_lets_anyone_in(self):
        with patch("api.views.run_sync") as run:
            self.assertEqual(self.client.get("/api/sync/?token=").status_code, 403)
            self.assertEqual(self.client.get("/api/sync/").status_code, 403)
            run.assert_not_called()

    def test_correct_token_runs_the_sync(self):
        with patch("api.views.run_sync", return_value=self.GOOD_REPORT) as run:
            response = self.client.get("/api/sync/?token=secret-token")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        run.assert_called_once()

    def test_token_in_a_header_also_works(self):
        with patch("api.views.run_sync", return_value=self.GOOD_REPORT):
            response = self.client.get("/api/sync/", HTTP_X_SYNC_TOKEN="secret-token")
        self.assertEqual(response.status_code, 200)

    def test_post_with_token_also_works(self):
        with patch("api.views.run_sync", return_value=self.GOOD_REPORT):
            response = self.client.post("/api/sync/?token=secret-token")
        self.assertEqual(response.status_code, 200)

    def test_api_trouble_returns_502_so_the_scheduler_flags_it(self):
        report = {**self.GOOD_REPORT, "errors": ["scores week 4: boom"]}
        with patch("api.views.run_sync", return_value=report):
            response = self.client.get("/api/sync/?token=secret-token")
        self.assertEqual(response.status_code, 502)
        self.assertFalse(response.json()["ok"])

    def test_a_crash_returns_500(self):
        with patch("api.views.run_sync", side_effect=RuntimeError("bug")):
            response = self.client.get("/api/sync/?token=secret-token")
        self.assertEqual(response.status_code, 500)


# ------------------------------------------------------ the sync_nfl command --

@override_settings(**SETTINGS)
class SyncCommandTests(TestCase):
    def run_command(self, fake, *args):
        out = StringIO()
        with patch("api.services._get", fake):
            call_command("sync_nfl", *args, stdout=out)
        return out.getvalue()

    def test_week_option_prints_a_summary(self):
        fake = FakeApi(schedules={2: [raw_game("G1", "KC", "BAL", hours_from_now(48))]}, scores={2: {}})
        output = self.run_command(fake, "--week", "2")
        self.assertIn("Week 2: 1 games, 1 with kickoff times, 0 final", output)

    def test_warns_when_no_kickoff_times_come_back(self):
        fake = FakeApi(schedules={2: [raw_game("G1", "KC", "BAL", None)]}, scores={2: {}})
        output = self.run_command(fake, "--week", "2")
        self.assertIn("No kickoff times came back", output)

    def test_through_loads_every_week_up_to_n(self):
        fake = FakeApi()
        self.run_command(fake, "--through", "2")
        self.assertEqual(len(fake.calls), 4)   # schedule + scores for weeks 1 and 2

    def test_bad_week_number_is_rejected(self):
        with self.assertRaises(CommandError):
            self.run_command(FakeApi(), "--week", "25")

    def test_api_failure_becomes_a_clear_command_error(self):
        with self.assertRaises(CommandError):
            self.run_command(FakeApi(error="boom"), "--week", "2")
