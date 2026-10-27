from datetime import date
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cyrus_intake.schedule import scheduled_week  # noqa: E402


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.week_one = date(2026, 9, 13)

    def test_week_six_sunday(self):
        self.assertEqual(scheduled_week(date(2026, 10, 18), self.week_one), 6)

    def test_week_seven_sunday(self):
        self.assertEqual(scheduled_week(date(2026, 10, 25), self.week_one), 7)

    def test_midweek_stays_in_same_nfl_week(self):
        self.assertEqual(scheduled_week(date(2026, 10, 28), self.week_one), 7)

    def test_week_one_is_not_automated(self):
        self.assertIsNone(scheduled_week(date(2026, 9, 13), self.week_one))

    def test_week_eighteen_is_supported(self):
        self.assertEqual(scheduled_week(date(2027, 1, 10), self.week_one), 18)

    def test_after_week_eighteen_is_skipped(self):
        self.assertIsNone(scheduled_week(date(2027, 1, 17), self.week_one))


if __name__ == "__main__":
    unittest.main()
