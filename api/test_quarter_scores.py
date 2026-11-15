"""Pure tests for api.rules.parse_quarter_scores (no database, no network)."""
import unittest

from api import rules


def box(home, away, period=None):
    body = {"lineScore": {
        "home": {f"Q{i + 1}": str(v) for i, v in enumerate(home)},
        "away": {f"Q{i + 1}": str(v) for i, v in enumerate(away)},
    }}
    if period is not None:
        body["currentPeriod"] = period
    return body


class QuarterScoreParsingTests(unittest.TestCase):
    def test_in_progress_quarter_is_never_recorded(self):
        # Q1 over, Q2 just started 0-0: Q2 must not be recorded as complete.
        out = rules.parse_quarter_scores(box([7, 0, 0, 0], [3, 0, 0, 0], "Q2"))
        self.assertEqual(out, {1: (7, 3)})

    def test_period_alone_marks_earlier_quarters_complete(self):
        out = rules.parse_quarter_scores(box([7, 3, 0, 0], [0, 0, 0, 0], "3rd"))
        self.assertEqual(out, {1: (7, 0), 2: (10, 0)})

    def test_later_scoring_marks_quarter_complete_without_period(self):
        out = rules.parse_quarter_scores(box([0, 0, 7, 0], [0, 3, 0, 0]))
        # Q3 points alone do not prove Q3 is over, so only Q1 and Q2 are recorded.
        self.assertEqual(out, {1: (0, 0), 2: (0, 3)})

    def test_unsure_returns_nothing_for_unfinished_quarter(self):
        self.assertEqual(rules.parse_quarter_scores(box([7, 0, 0, 0], [0, 0, 0, 0])), {})

    def test_final_records_all_three_cumulative(self):
        out = rules.parse_quarter_scores(box([7, 3, 7, 3], [0, 10, 0, 7]), final=True)
        self.assertEqual(out, {1: (7, 0), 2: (10, 10), 3: (17, 10)})

    def test_clock_text_is_not_read_as_period(self):
        self.assertIsNone(rules._current_period({"currentPeriod": "5:00 2nd"}))
        self.assertEqual(rules._current_period({"currentPeriod": "Q4"}), 4)

    def test_bad_input(self):
        for bad in (None, [], {}, {"lineScore": "x"}, {"lineScore": {"home": {}, "away": {}}}):
            self.assertEqual(rules.parse_quarter_scores(bad, final=True), {})


if __name__ == "__main__":
    unittest.main()
