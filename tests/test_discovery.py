import unittest

from cyrus_intake.discovery import CIRCA_PAGE, WESTGATE_PAGES, _request_url, discover_urls
from cyrus_intake.parser import IntakeError


def westgate_html(filename, href):
    return f"<table><tr><td>{filename}</td><td><a href='{href}'>Download</a></td></tr></table>"


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.pages = {
            WESTGATE_PAGES["westgate_card"].format(season=2026): westgate_html(
                "2026 SUPERCONTEST GAME SHEET WK 6.pdf", "/supercontest/download/card.pdf"
            ),
            WESTGATE_PAGES["westgate_selections"].format(season=2026): westgate_html(
                "2026 SUPERCONTEST SELECTIONS WEEK 6.pdf", "/supercontest/download/selections.pdf"
            ),
            WESTGATE_PAGES["westgate_standings"].format(season=2026): westgate_html(
                "2026 SuperContest Standings Week 5.pdf", "/supercontest/download/standings.pdf"
            ),
            CIRCA_PAGE: """
                <blockquote class='twitter-tweet'><p>
                  #CircaSportsMillion VIII Week 6 Selections
                  <a href='https://t.co/selection'>PDF</a>
                  <a href='https://t.co/image'>image</a>
                </p></blockquote>
                <blockquote class='twitter-tweet'><p>
                  #CircaSportsMillion VIII Week 5 Standings Update
                  Full Season: <a href='https://t.co/standings'>PDF</a>
                  2nd Quarter: <a href='https://t.co/quarter'>PDF</a>
                </p></blockquote>
            """,
        }
        self.redirects = {
            "https://t.co/selection": "https://www.circasports.com/uploads/week-6-selections.pdf",
            "https://t.co/image": "https://www.circasports.com/uploads/week-6.jpg",
            "https://t.co/standings": "https://www.circasports.com/uploads/standings-week-5.pdf",
            "https://t.co/quarter": "https://www.circasports.com/uploads/quarter.pdf",
        }

    def test_discovers_exact_week_sources(self):
        result = discover_urls(
            2026,
            6,
            get_text=self.pages.__getitem__,
            resolve_url=self.redirects.__getitem__,
        )
        self.assertEqual(result["circa_selections"], self.redirects["https://t.co/selection"])
        self.assertEqual(result["circa_standings"], self.redirects["https://t.co/standings"])
        self.assertTrue(result["westgate_card"].endswith("/supercontest/download/card.pdf"))

    def test_discovers_plain_text_tweet_pdf_links(self):
        pages = dict(self.pages)
        pages[CIRCA_PAGE] = """
            <blockquote class='twitter-tweet'><p>
              #CircaSportsMillion VIII Week 6 Selections
              PDF: https://t.co/selection
              <a href='https://t.co/image'>promotional image</a>
            </p></blockquote>
            <blockquote class='twitter-tweet'><p>
              #CircaSportsMillion VIII Week 5 Standings Update
              Full Season: https://t.co/standings
              2nd Quarter: https://t.co/quarter
            </p></blockquote>
        """
        result = discover_urls(
            2026,
            6,
            get_text=pages.__getitem__,
            resolve_url=self.redirects.__getitem__,
        )
        self.assertEqual(result["circa_selections"], self.redirects["https://t.co/selection"])
        self.assertEqual(result["circa_standings"], self.redirects["https://t.co/standings"])

    def test_plain_text_non_official_link_is_ignored(self):
        pages = dict(self.pages)
        pages[CIRCA_PAGE] = """
            <blockquote class='twitter-tweet'><p>
              #CircaSportsMillion VIII Week 6 Selections
              PDF: https://example.com/not-official.pdf
            </p></blockquote>
            <blockquote class='twitter-tweet'><p>
              #CircaSportsMillion VIII Week 5 Standings Update
              Full Season: https://t.co/standings
            </p></blockquote>
        """
        with self.assertRaisesRegex(IntakeError, "no resolvable official PDF link"):
            discover_urls(2026, 6, get_text=pages.__getitem__, resolve_url=self.redirects.__getitem__)

    def test_official_url_spaces_are_encoded_once(self):
        raw = (
            "https://www.westgateresorts.com/supercontest/download/"
            "2026 SUPERCONTEST GAME SHEET WK 6.pdf?contest=/2026/SuperContest/Card"
        )
        self.assertEqual(
            _request_url(raw),
            "https://www.westgateresorts.com/supercontest/download/"
            "2026%20SUPERCONTEST%20GAME%20SHEET%20WK%206.pdf?contest=/2026/SuperContest/Card",
        )
        self.assertEqual(_request_url(_request_url(raw)), _request_url(raw))

    def test_missing_current_week_refuses(self):
        pages = dict(self.pages)
        card_page = WESTGATE_PAGES["westgate_card"].format(season=2026)
        pages[card_page] = westgate_html(
            "2026 SUPERCONTEST GAME SHEET WK 5.pdf", "/supercontest/download/card5.pdf"
        )
        with self.assertRaisesRegex(IntakeError, "expected one westgate_card"):
            discover_urls(2026, 6, get_text=pages.__getitem__, resolve_url=self.redirects.__getitem__)

    def test_duplicate_week_source_refuses(self):
        pages = dict(self.pages)
        selection_page = WESTGATE_PAGES["westgate_selections"].format(season=2026)
        pages[selection_page] += westgate_html(
            "2026 SUPERCONTEST SELECTIONS WK 6.pdf", "/supercontest/download/duplicate.pdf"
        )
        with self.assertRaisesRegex(IntakeError, "found 2"):
            discover_urls(2026, 6, get_text=pages.__getitem__, resolve_url=self.redirects.__getitem__)

    def test_week_one_refuses_instead_of_inheriting(self):
        with self.assertRaisesRegex(IntakeError, "weeks 2-18"):
            discover_urls(2026, 1, get_text=self.pages.__getitem__, resolve_url=self.redirects.__getitem__)


if __name__ == "__main__":
    unittest.main()
