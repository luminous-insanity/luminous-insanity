# api/test_rules.py
# Run with:  python manage.py test api      (or:  python -m unittest api.test_rules)
import unittest
from datetime import date, datetime, timezone

from . import rules


class StatusTests(unittest.TestCase):
    def test_final_by_code_or_text(self):
        self.assertEqual(rules.normalize_status({"gameStatusCode": "2"}), rules.FINAL)
        self.assertEqual(rules.normalize_status({"gameStatus": "Completed"}), rules.FINAL)
        self.assertEqual(rules.normalize_status({"gameStatus": "Final"}), rules.FINAL)

    def test_live_and_not_started(self):
        self.assertEqual(rules.normalize_status({"gameStatusCode": "1"}), rules.LIVE)
        self.assertEqual(rules.normalize_status({"gameStatus": "Live - In Progress"}), rules.LIVE)
        self.assertEqual(rules.normalize_status({"gameStatusCode": "0"}), rules.SCHEDULED)
        self.assertEqual(rules.normalize_status({}), rules.SCHEDULED)

    def test_suspended_is_not_final(self):
        self.assertEqual(rules.normalize_status({"gameStatusCode": "4", "gameStatus": "Suspended"}),
                         rules.SCHEDULED)


class ParseTests(unittest.TestCase):
    def test_score_final(self):
        got = rules.parse_score({"gameStatusCode": "2", "homePts": "27", "awayPts": "20"})
        self.assertEqual(got, {"status": "final", "home_score": 27, "away_score": 20})

    def test_final_without_scores_is_not_final(self):
        got = rules.parse_score({"gameStatusCode": "2", "homePts": "", "awayPts": None})
        self.assertEqual(got["status"], rules.LIVE)
        self.assertIsNone(got["home_score"])

    def test_not_started_has_no_scores(self):
        got = rules.parse_score({"gameStatusCode": "0", "homePts": "", "awayPts": ""})
        self.assertEqual(got, {"status": "scheduled", "home_score": None, "away_score": None})

    def test_game_with_kickoff(self):
        epoch = datetime(2026, 9, 14, 0, 15, tzinfo=timezone.utc).timestamp()
        got = rules.parse_game({"gameID": "20260913_BAL@KC", "home": "KC", "away": "BAL",
                                "gameDate": "20260913", "gameTime_epoch": str(epoch)})
        self.assertEqual(got["game_date"], date(2026, 9, 13))
        self.assertEqual(got["kickoff"], datetime(2026, 9, 14, 0, 15, tzinfo=timezone.utc))

    def test_game_without_kickoff_or_bad_data(self):
        good = {"gameID": "x", "home": "KC", "away": "BAL", "gameDate": "20260913"}
        self.assertIsNone(rules.parse_game(good)["kickoff"])
        self.assertIsNone(rules.parse_game({**good, "gameDate": "garbage"}))
        self.assertIsNone(rules.parse_game({**good, "home": None}))


class GradeTests(unittest.TestCase):
    def test_grading(self):
        self.assertEqual(rules.grade_pick("home", 27, 20), "win")
        self.assertEqual(rules.grade_pick("away", 27, 20), "loss")
        self.assertEqual(rules.grade_pick("away", 3, 24), "win")
        self.assertEqual(rules.grade_pick("home", 20, 20), "tie")
        self.assertEqual(rules.grade_pick("away", 20, 20), "tie")

    def test_no_score_means_no_grade(self):
        self.assertIsNone(rules.grade_pick("home", None, None))
        self.assertIsNone(rules.grade_pick("home", 7, None))

    def test_grading_twice_gives_same_answer(self):
        # The old running-total code could not promise this.
        self.assertEqual(rules.grade_pick("home", 27, 20), rules.grade_pick("home", 27, 20))


class LockTests(unittest.TestCase):
    def test_real_kickoff_wins(self):
        k = datetime(2026, 9, 14, 0, 15, tzinfo=timezone.utc)
        self.assertEqual(rules.lock_time(k, date(2026, 9, 13)), k)

    def test_fallback_is_9am_eastern_game_day(self):
        got = rules.lock_time(None, date(2026, 9, 13))
        self.assertEqual(got.astimezone(timezone.utc), datetime(2026, 9, 13, 13, 0, tzinfo=timezone.utc))


class CurrentWeekTests(unittest.TestCase):
    TODAY = date(2026, 10, 7)  # a Wednesday

    def test_nothing_loaded_is_week_1(self):
        self.assertEqual(rules.choose_current_week([], self.TODAY), 1)

    def test_lowest_week_with_unfinished_game(self):
        games = [(3, "final", date(2026, 9, 28)), (4, "live", date(2026, 10, 5)),
                 (4, "scheduled", date(2026, 10, 6)), (5, "scheduled", date(2026, 10, 11))]
        self.assertEqual(rules.choose_current_week(games, self.TODAY), 4)

    def test_moves_on_after_monday_night_final(self):
        games = [(4, "final", date(2026, 10, 5)), (5, "scheduled", date(2026, 10, 11))]
        self.assertEqual(rules.choose_current_week(games, self.TODAY), 5)

    def test_stays_on_last_week_until_next_is_loaded(self):
        games = [(4, "final", date(2026, 10, 5))]
        self.assertEqual(rules.choose_current_week(games, self.TODAY), 4)

    def test_old_postponed_game_cannot_trap_the_site(self):
        games = [(3, "scheduled", date(2026, 9, 27)),   # never finished, 10 days old
                 (4, "final", date(2026, 10, 5)), (5, "scheduled", date(2026, 10, 11))]
        self.assertEqual(rules.choose_current_week(games, self.TODAY), 5)


if __name__ == "__main__":
    unittest.main()
