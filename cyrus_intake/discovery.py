"""Discover and download the official weekly contest PDFs.

Only fixed Westgate and Circa pages are requested.  The service has no
user-supplied URL input, and every downloaded PDF must finish on an approved
official host before its bytes are handed to the parser.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from http.client import InvalidURL
import re
import time
from typing import Callable, Dict, Iterable, List, Mapping, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .parser import IntakeError


USER_AGENT = "CyrusContestIntake/1.0 (+owner-operated staging service)"
MAX_HTML_BYTES = 4 * 1024 * 1024
MAX_PDF_BYTES = 30 * 1024 * 1024
TIMEOUT_SECONDS = 35

WESTGATE_PAGES = {
    "westgate_card": "https://www.westgateresorts.com/hotels/nevada/las-vegas/"
    "westgate-las-vegas-resort-casino/casino/{season}-supercontest-card/",
    "westgate_selections": "https://www.westgateresorts.com/hotels/nevada/las-vegas/"
    "westgate-las-vegas-resort-casino/casino/{season}-supercontest-selections/",
    "westgate_standings": "https://www.westgateresorts.com/hotels/nevada/las-vegas/"
    "westgate-las-vegas-resort-casino/casino/{season}-supercontest-standings",
}
CIRCA_PAGE = "https://www.circasports.com/circa-million"

APPROVED_FINAL_HOSTS = {
    "www.westgateresorts.com",
    "westgateresorts.com",
    "www.circasports.com",
    "circasports.com",
}


@dataclass(frozen=True)
class LinkGroup:
    text: str
    links: Tuple[str, ...]


class _OfficialPageParser(HTMLParser):
    """Collect table rows and embedded tweet blockquotes with their links."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: List[LinkGroup] = []
        self.quotes: List[LinkGroup] = []
        self._row_depth = 0
        self._quote_depth = 0
        self._row_text: List[str] = []
        self._row_links: List[str] = []
        self._quote_text: List[str] = []
        self._quote_links: List[str] = []

    def handle_starttag(self, tag: str, attrs: Sequence[Tuple[str, str | None]]) -> None:
        values = {key.lower(): (value or "") for key, value in attrs}
        if tag.lower() == "tr":
            if self._row_depth == 0:
                self._row_text, self._row_links = [], []
            self._row_depth += 1
        if tag.lower() == "blockquote":
            classes = values.get("class", "").split()
            if "twitter-tweet" in classes or self._quote_depth:
                if self._quote_depth == 0:
                    self._quote_text, self._quote_links = [], []
                self._quote_depth += 1
        if tag.lower() == "a" and values.get("href"):
            if self._row_depth:
                self._row_links.append(values["href"])
            if self._quote_depth:
                self._quote_links.append(values["href"])

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "tr" and self._row_depth:
            self._row_depth -= 1
            if self._row_depth == 0:
                self.rows.append(LinkGroup(_space(" ".join(self._row_text)), tuple(self._row_links)))
        if tag.lower() == "blockquote" and self._quote_depth:
            self._quote_depth -= 1
            if self._quote_depth == 0:
                self.quotes.append(LinkGroup(_space(" ".join(self._quote_text)), tuple(self._quote_links)))

    def handle_data(self, data: str) -> None:
        if self._row_depth:
            self._row_text.append(data)
        if self._quote_depth:
            self._quote_text.append(data)


def discover_urls(
    season: int,
    week: int,
    *,
    get_text: Callable[[str], str] | None = None,
    resolve_url: Callable[[str], str] | None = None,
) -> Dict[str, str]:
    """Return the five official source URLs needed for one weekly stage."""
    if not (2 <= int(week) <= 18):
        raise IntakeError("automated discovery supports weeks 2-18")
    get_text = get_text or fetch_text
    resolve_url = resolve_url or resolve_official_url

    urls: Dict[str, str] = {}
    predicates = {
        "westgate_card": re.compile(rf"\b(?:WEEK|WK)\s*{week}\b", re.I),
        "westgate_selections": re.compile(rf"\b(?:WEEK|WK)\s*{week}\b", re.I),
        "westgate_standings": re.compile(rf"\b(?:WEEK|WK)\s*{week - 1}\b", re.I),
    }
    for kind, template in WESTGATE_PAGES.items():
        page_url = template.format(season=season)
        group = _find_unique_group(
            _parse_page(get_text(page_url)).rows,
            lambda item, p=predicates[kind]: str(season) in item.text and bool(p.search(item.text)) and ".pdf" in item.text.lower(),
            f"{kind} for {season} week {week}",
        )
        candidates = [urljoin(page_url, href) for href in group.links if "download" in href.lower() or ".pdf" in href.lower()]
        if len(candidates) != 1:
            raise IntakeError(f"{kind} row must contain one PDF download; found {len(candidates)}")
        urls[kind] = candidates[0]

    circa_groups = _parse_page(get_text(CIRCA_PAGE)).quotes
    selections = _find_unique_group(
        circa_groups,
        lambda item: bool(re.search(rf"\bWeek\s*{week}\s+Selections\b", item.text, re.I)),
        f"Circa Week {week} selections post",
    )
    standings = _find_unique_group(
        circa_groups,
        lambda item: bool(re.search(rf"\bWeek\s*{week - 1}\s+Standings\b", item.text, re.I)),
        f"Circa Week {week - 1} standings post",
    )
    urls["circa_selections"] = _resolve_first_pdf_link(
        _candidate_links(selections), resolve_url, "Circa selections"
    )
    urls["circa_standings"] = _resolve_first_pdf_link(
        _candidate_links(standings), resolve_url, "Circa standings"
    )
    return urls


def fetch_sources(urls: Mapping[str, str]) -> Dict[str, bytes]:
    expected = {
        "westgate_standings",
        "westgate_selections",
        "westgate_card",
        "circa_standings",
        "circa_selections",
    }
    if set(urls) != expected:
        raise IntakeError(f"source URL set is incomplete: expected={sorted(expected)}, actual={sorted(urls)}")
    return {kind: fetch_pdf(url) for kind, url in urls.items()}


def fetch_text(url: str) -> str:
    data, final_url, content_type = _read_url(url, MAX_HTML_BYTES)
    _require_host(final_url, {urlparse(url).hostname or ""})
    if "html" not in content_type.lower() and not data.lstrip().startswith(b"<"):
        raise IntakeError(f"official page did not return HTML: {url}")
    return data.decode("utf-8", errors="replace")


def fetch_pdf(url: str) -> bytes:
    data, final_url, _content_type = _read_url(url, MAX_PDF_BYTES)
    _require_host(final_url, APPROVED_FINAL_HOSTS)
    if not data.startswith(b"%PDF"):
        raise IntakeError(f"official PDF URL did not return a PDF: {url}")
    return data


def resolve_official_url(url: str) -> str:
    # GET a small response because some t.co endpoints reject HEAD.  urllib
    # follows redirects; the final host must be official.
    _data, final_url, _content_type = _read_url(url, MAX_PDF_BYTES)
    _require_host(final_url, APPROVED_FINAL_HOSTS)
    return final_url


def _read_url(url: str, limit: int) -> Tuple[bytes, str, str]:
    try:
        request = Request(
            _request_url(url),
            headers={"User-Agent": USER_AGENT, "Accept": "application/pdf,text/html;q=0.9,*/*;q=0.1"},
        )
    except (InvalidURL, ValueError) as exc:
        raise IntakeError(f"invalid official source URL: {exc}") from exc
    last: Exception | None = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                declared = int(response.headers.get("Content-Length", "0") or 0)
                if declared > limit:
                    raise IntakeError(f"response exceeds {limit} bytes: {url}")
                data = response.read(limit + 1)
                if len(data) > limit:
                    raise IntakeError(f"response exceeds {limit} bytes: {url}")
                return data, response.geturl(), response.headers.get("Content-Type", "")
        except (HTTPError, URLError, TimeoutError, InvalidURL, ValueError) as exc:
            last = exc
            if attempt < 2:
                time.sleep(0.4 * (2**attempt))
    raise IntakeError(f"could not fetch official source {url}: {last}")


def _request_url(url: str) -> str:
    """Encode unsafe path/query characters without double-encoding escapes."""
    parts = urlsplit(url)
    path = quote(parts.path, safe="/%:@-._~!$&'()*+,;=")
    query = quote(parts.query, safe="=&/%:@?+-._~!$'()*,;")
    return urlunsplit((parts.scheme, parts.netloc, path, query, ""))


def _parse_page(html: str) -> _OfficialPageParser:
    parser = _OfficialPageParser()
    parser.feed(html)
    return parser


def _find_unique_group(groups: Iterable[LinkGroup], predicate: Callable[[LinkGroup], bool], label: str) -> LinkGroup:
    matches = [group for group in groups if predicate(group)]
    if len(matches) != 1:
        raise IntakeError(f"expected one {label}; found {len(matches)}")
    return matches[0]


def _candidate_links(group: LinkGroup) -> Tuple[str, ...]:
    """Return embedded and visible URLs in their first-seen order.

    X/Twitter's embed markup may leave the document link as plain tweet text
    while only making the attached image clickable.  Plain-text URLs still go
    through the same redirect and approved-final-host checks as hrefs.
    """
    values = list(group.links)
    values.extend(re.findall(r"https?://[^\s<>\"']+", group.text))
    return tuple(dict.fromkeys(value.rstrip(".,);]") for value in values))


def _resolve_first_pdf_link(links: Sequence[str], resolve_url: Callable[[str], str], label: str) -> str:
    failures: List[str] = []
    for link in links:
        host = (urlparse(link).hostname or "").lower()
        if host not in {"t.co", "www.circasports.com", "circasports.com"}:
            continue
        try:
            final = resolve_url(link)
        except Exception as exc:  # try the next link in an official embedded post
            failures.append(str(exc))
            continue
        if urlparse(final).path.lower().endswith(".pdf"):
            return final
    raise IntakeError(f"{label} post has no resolvable official PDF link; failures={failures}")


def _require_host(url: str, allowed: Iterable[str]) -> None:
    host = (urlparse(url).hostname or "").lower()
    normalized = {item.lower() for item in allowed}
    if host not in normalized:
        raise IntakeError(f"refused non-official redirect host {host or '(missing)'}")


def _space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
