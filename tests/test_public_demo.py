from datetime import date, datetime
import os
import unittest
from unittest import mock

import app as service
from cyrus_intake.parser import IntakeError, pdf_pages
from cyrus_intake.schedule import scheduled_week
from examples.offline_demo import agreement, make_bundle, synthetic_sources


class PublicDemoTests(unittest.TestCase):
    def test_bundle_and_ties(self):
        bundle = make_bundle()
        self.assertEqual(len(bundle["contestDataRows"]), 8)
        self.assertEqual(len(bundle["lineRows"]), 28)
        self.assertEqual(bundle["status"], "STAGED_NOT_LOADED")
        self.assertTrue(all(r["expectedTieSize"] == 2 for r in bundle["contestDataRows"]))

    def test_agreement_counts(self):
        summary = agreement(make_bundle())
        self.assertEqual(summary["Westgate"]["entries"], 4)
        self.assertEqual(summary["Westgate"]["counts"]["Arizona Cardinals"], 2)

    def test_missing_leader_refuses(self):
        sources = synthetic_sources()
        sources["westgate_selections"] = sources["westgate_selections"].replace("SAMPLE-A", "OTHER")
        with self.assertRaisesRegex(IntakeError, "missing leading entry"):
            make_bundle(sources)

    def test_hash_same_inputs_but_timestamp_matters(self):
        first = make_bundle()["bundleSha256"]
        self.assertEqual(first, make_bundle()["bundleSha256"])
        self.assertNotEqual(first, make_bundle(timestamp="2026-10-27T12:00:01Z")["bundleSha256"])

    def test_real_pdf_boundary_rejects_text(self):
        with self.assertRaisesRegex(IntakeError, "not a PDF"):
            pdf_pages(b"synthetic plain text")

    def test_saturday_boundaries(self):
        for day, week in [(date(2026, 10, 24), 7), (date(2026, 10, 31), 8), (date(2026, 11, 7), 9)]:
            with self.subTest(day=day):
                self.assertEqual(scheduled_week(day, date(2026, 9, 12)), week)

    def test_saturday_route(self):
        env = {"SCHEDULE_SEASON": "2026", "SCHEDULE_WEEK1_DATE": "2026-09-12", "SCHEDULE_TIMEZONE": "America/Chicago"}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(service, "datetime") as clock, mock.patch.object(service, "_stage", return_value={"ok": True}) as stage:
            clock.now.return_value = datetime.fromisoformat("2026-10-31T20:00:00-05:00")
            response = service.app.test_client().post("/scheduled")
        self.assertEqual(response.status_code, 200)
        stage.assert_called_once_with(2026, 8, True)

    def test_both_routes_log_refusals(self):
        client = service.app.test_client()
        env = {"SCHEDULE_SEASON": "2026", "SCHEDULE_WEEK1_DATE": "2026-09-12"}
        for route in ["/run?season=2026&week=8", "/scheduled"]:
            with self.subTest(route=route), mock.patch.dict(os.environ, env, clear=True), mock.patch.object(service, "datetime") as clock, mock.patch.object(service, "_stage", side_effect=IntakeError("synthetic refusal")), self.assertLogs(service.app.logger, level="WARNING") as logs:
                clock.now.return_value = datetime.fromisoformat("2026-10-31T20:00:00-05:00")
                response = client.post(route)
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.get_json()["status"], "REFUSED_NO_WRITE")
            self.assertIn("synthetic refusal", " ".join(logs.output))
