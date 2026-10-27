from datetime import datetime
import os
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app as service  # noqa: E402


SCHEDULE_ENV = {
    "SCHEDULE_SEASON": "2026",
    "SCHEDULE_WEEK1_DATE": "2026-09-13",
    "SCHEDULE_TIMEZONE": "America/Chicago",
}


class ServiceRouteTests(unittest.TestCase):
    def setUp(self):
        service.app.config.update(TESTING=True)
        self.client = service.app.test_client()

    def test_scheduled_route_stages_current_week_with_write_enabled(self):
        fixed_now = datetime.fromisoformat("2026-10-18T10:30:00-05:00")
        with (
            mock.patch.dict(os.environ, SCHEDULE_ENV, clear=True),
            mock.patch.object(service, "datetime") as service_datetime,
            mock.patch.object(
                service,
                "_stage",
                return_value={"ok": True, "writeRequested": True, "week": 6},
            ) as stage,
        ):
            service_datetime.now.return_value = fixed_now
            response = self.client.post("/scheduled")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["week"], 6)
        stage.assert_called_once_with(2026, 6, True)

    def test_scheduled_route_skips_without_write_outside_supported_weeks(self):
        fixed_now = datetime.fromisoformat("2027-01-17T10:30:00-06:00")
        with (
            mock.patch.dict(os.environ, SCHEDULE_ENV, clear=True),
            mock.patch.object(service, "datetime") as service_datetime,
            mock.patch.object(service, "_stage") as stage,
        ):
            service_datetime.now.return_value = fixed_now
            response = self.client.post("/scheduled")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "SKIPPED_OUTSIDE_SUPPORTED_WEEKS")
        self.assertFalse(response.get_json()["writeRequested"])
        stage.assert_not_called()

    def test_scheduled_route_refuses_when_required_env_is_missing(self):
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(service, "_stage") as stage,
        ):
            response = self.client.post("/scheduled")

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.get_json()["status"], "REFUSED_NO_WRITE")
        stage.assert_not_called()

    def test_scheduled_route_refuses_invalid_timezone(self):
        env = dict(SCHEDULE_ENV, SCHEDULE_TIMEZONE="Not/A_Timezone")
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(service, "_stage") as stage,
        ):
            response = self.client.post("/scheduled")

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.get_json()["status"], "REFUSED_NO_WRITE")
        stage.assert_not_called()

    def test_owner_run_route_keeps_preview_default(self):
        with mock.patch.object(
            service,
            "_stage",
            return_value={"ok": True, "writeRequested": False, "week": 7},
        ) as stage:
            response = self.client.post("/run?season=2026&week=7")

        self.assertEqual(response.status_code, 200)
        stage.assert_called_once_with(2026, 7, False)


if __name__ == "__main__":
    unittest.main()
