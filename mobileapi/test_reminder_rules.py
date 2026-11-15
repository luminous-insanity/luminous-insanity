"""Pure tests for the weekly reminder rules (no database)."""
import unittest
from datetime import datetime, timedelta, timezone

from mobileapi.reminder_rules import EASTERN, first_day_games, reminder_due, reminder_text

UTC = timezone.utc
# Thursday 8:15 PM Eastern (EDT, UTC-4) = Friday 00:15 UTC
THU = datetime(2026, 9, 11, 0, 15, tzinfo=UTC)
SUN = datetime(2026, 9, 13, 17, 0, tzinfo=UTC)


class ReminderRuleTests(unittest.TestCase):
    def test_first_day_is_thursday_only(self):
        first, ids = first_day_games([("sun1", SUN), ("thu", THU), ("sun2", SUN)])
        self.assertEqual(first, THU)
        self.assertEqual(ids, ["thu"])

    def test_day_is_eastern_not_utc(self):
        # Two games that are on the same Eastern day but different UTC dates.
        a = datetime(2026, 9, 13, 22, 0, tzinfo=UTC)   # Sun 6:00 PM ET
        b = datetime(2026, 9, 14, 0, 20, tzinfo=UTC)   # Sun 8:20 PM ET
        first, ids = first_day_games([("a", a), ("b", b)])
        self.assertEqual(sorted(ids), ["a", "b"])
        self.assertEqual(first, a)

    def test_window_is_two_hours_before_kickoff_until_kickoff(self):
        self.assertFalse(reminder_due(THU, THU - timedelta(hours=2, seconds=1)))
        self.assertTrue(reminder_due(THU, THU - timedelta(hours=2)))
        self.assertTrue(reminder_due(THU, THU - timedelta(minutes=1)))
        self.assertFalse(reminder_due(THU, THU))

    def test_moved_kickoff_moves_the_window(self):
        later = THU + timedelta(hours=3)
        now = THU - timedelta(minutes=30)
        self.assertTrue(reminder_due(THU, now))
        self.assertFalse(reminder_due(later, now))

    def test_ignores_games_without_lock_time_and_empty(self):
        self.assertIsNone(first_day_games([]))
        self.assertIsNone(first_day_games([("x", None)]))
        first, ids = first_day_games([("x", None), ("thu", THU)])
        self.assertEqual(ids, ["thu"])

    def test_text_names_the_day(self):
        title, body = reminder_text(THU)
        self.assertIn("Thursday", body)
        self.assertEqual(THU.astimezone(EASTERN).strftime("%A"), "Thursday")  # 00:15 UTC Fri = Thu 8:15 PM ET
        self.assertEqual(THU.strftime("%A"), "Friday")


if __name__ == "__main__":
    unittest.main()
