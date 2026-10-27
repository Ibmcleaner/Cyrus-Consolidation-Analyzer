import copy
import json
import os
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cyrus_intake.parser import (  # noqa: E402
    IntakeError,
    build_bundle,
    parse_leading_standings,
    pdf_pages,
)


UPLOAD = Path(os.environ.get("CYRUS_FIXTURE_DIR", str(ROOT / "private-fixtures")))


FILES = {
    "westgate_standings": UPLOAD / "2026 SuperContest Standings Week 5.pdf",
    "westgate_selections": UPLOAD / "2026 SUPERCONTEST SELECTIONS WEEK 6.pdf",
    "westgate_card": UPLOAD / "2026 SUPERCONTEST GAME SHEET WK 6.pdf",
    "circa_standings": UPLOAD / "Circa-Sports-Million-VIII-Full-Season-Standings-After-Week-5.pdf",
    "circa_selections": UPLOAD / "Circa-Sports-Million-VIII-Week-6-Selections.pdf",
}


URLS = {name: f"https://official.example/{path.name}" for name, path in FILES.items()}


def week6_bundle():
    raw = {name: path.read_bytes() for name, path in FILES.items()}
    return build_bundle(
        season=2026,
        week=6,
        urls=URLS,
        generated_at_utc="2026-10-18T16:30:00Z",
        **raw,
    )


@unittest.skipUnless(os.environ.get("CYRUS_FIXTURE_DIR"),
                     "Historical PDFs excluded; set CYRUS_FIXTURE_DIR to run these 7 tests")
class ParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = week6_bundle()

    def test_week6_matches_verified_leader_pool(self):
        rows = self.bundle["contestDataRows"]
        self.assertEqual(
            [(r["contest"], r["sourcePlace"], r["alias"]) for r in rows],
            [
                ("Westgate", 1, "RIGGED NFL-1"),
                ("Westgate", 2, "2 P.I.C.-2"),
                ("Westgate", 2, "HIPPOBOY320-1"),
                ("Circa", 1, "PARLAYSAM-2"),
                ("Circa", 1, "WILD TERPS-1"),
                ("Circa", 3, "BEEBTHEFROG-2"),
                ("Circa", 3, "RPB4FUN-1"),
            ],
        )

    def test_week6_matches_verified_records_picks_and_lines(self):
        rows = {r["alias"]: r for r in self.bundle["contestDataRows"]}
        expected = {
            "RIGGED NFL-1": (
                "19-6-0-0",
                ["Seattle Seahawks", "Houston Texans", "New York Jets", "Cleveland Browns", "Carolina Panthers"],
                [-2.5, 2.5, 7.0, 5.5, 1.5],
            ),
            "2 P.I.C.-2": (
                "18-6-1-0",
                ["Seattle Seahawks", "Houston Texans", "Atlanta Falcons", "Dallas Cowboys", "Washington Commanders"],
                [-2.5, 2.5, 3.0, 1.5, 7.5],
            ),
            "HIPPOBOY320-1": (
                "18-6-1-0",
                ["Denver Broncos", "Houston Texans", "New England Patriots", "Atlanta Falcons", "New Orleans Saints"],
                [2.5, 2.5, -7.0, 3.0, -1.5],
            ),
            "PARLAYSAM-2": (
                "20-4-1-0",
                ["New England Patriots", "Baltimore Ravens", "Philadelphia Eagles", "Buffalo Bills", "Dallas Cowboys"],
                [-7.0, -5.5, 1.0, -4.5, 1.0],
            ),
            "WILD TERPS-1": (
                "20-4-1-0",
                ["Cleveland Browns", "Carolina Panthers", "New Orleans Saints", "Las Vegas Raiders", "Los Angeles Chargers"],
                [5.5, -1.0, -1.0, 4.5, 8.0],
            ),
            "BEEBTHEFROG-2": (
                "19-5-1-0",
                ["Houston Texans", "Atlanta Falcons", "Tennessee Titans", "Las Vegas Raiders", "Los Angeles Chargers"],
                [2.5, 0.0, 7.0, 4.5, 8.0],
            ),
            "RPB4FUN-1": (
                "19-5-1-0",
                ["Denver Broncos", "Pittsburgh Steelers", "Cleveland Browns", "Carolina Panthers", "New Orleans Saints"],
                [2.5, -2.5, 5.5, -1.0, -1.0],
            ),
        }
        for alias, (record, picks, lines) in expected.items():
            self.assertEqual(rows[alias]["record"], record)
            self.assertEqual(rows[alias]["picks"], picks)
            self.assertEqual(rows[alias]["cardLines"], lines)

    def test_cards_cross_check_to_same_28_teams(self):
        line_rows = self.bundle["lineRows"]
        self.assertEqual(len(line_rows), 28)
        self.assertEqual(len({r["officialTeam"] for r in line_rows}), 28)
        self.assertEqual(len({r["game"] for r in line_rows}), 14)

    def test_stage_is_deterministic_and_not_marked_loaded(self):
        again = week6_bundle()
        self.assertEqual(self.bundle["bundleSha256"], again["bundleSha256"])
        self.assertEqual(self.bundle["status"], "STAGED_NOT_LOADED")
        self.assertTrue(all("owner approval pending" in r["sourceVerified"].lower() for r in self.bundle["contestDataRows"]))

    def test_whole_tie_group_crossing_top_three_is_kept(self):
        leaders = parse_leading_standings(pdf_pages(FILES["circa_standings"].read_bytes()))
        self.assertEqual([r.place for r in leaders], [1, 1, 3, 3])

    def test_wrong_or_truncated_source_refuses(self):
        raw = {name: path.read_bytes() for name, path in FILES.items()}
        raw["westgate_card"] = b"not a pdf"
        with self.assertRaisesRegex(IntakeError, "not a PDF"):
            build_bundle(
                season=2026,
                week=6,
                urls=URLS,
                generated_at_utc="2026-10-18T16:30:00Z",
                **raw,
            )

    def test_bundle_hash_covers_the_staged_data(self):
        changed = copy.deepcopy(self.bundle)
        original_hash = changed.pop("bundleSha256")
        canonical = json.dumps(changed, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        import hashlib

        self.assertEqual(hashlib.sha256(canonical.encode("utf-8")).hexdigest(), original_hash)
        changed["contestDataRows"][0]["alias"] = "ALTERED"
        changed_canonical = json.dumps(changed, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        self.assertNotEqual(hashlib.sha256(changed_canonical.encode("utf-8")).hexdigest(), original_hash)


if __name__ == "__main__":
    unittest.main()

