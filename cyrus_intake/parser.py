"""Fail-closed parsers for the Cyrus Westgate/Circa weekly intake.

The source PDFs are the evidence.  This module never writes to C1.  It produces a
deterministic staging bundle which a separate approval step can compare and load.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
from io import BytesIO
import json
import re
import uuid
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

from pypdf import PdfReader


TEAM_NAMES: Mapping[str, str] = {
    "CARDINALS": "Arizona Cardinals",
    "FALCONS": "Atlanta Falcons",
    "RAVENS": "Baltimore Ravens",
    "BILLS": "Buffalo Bills",
    "PANTHERS": "Carolina Panthers",
    "BEARS": "Chicago Bears",
    "BENGALS": "Cincinnati Bengals",
    "BROWNS": "Cleveland Browns",
    "COWBOYS": "Dallas Cowboys",
    "BRONCOS": "Denver Broncos",
    "LIONS": "Detroit Lions",
    "PACKERS": "Green Bay Packers",
    "TEXANS": "Houston Texans",
    "COLTS": "Indianapolis Colts",
    "JAGUARS": "Jacksonville Jaguars",
    "CHIEFS": "Kansas City Chiefs",
    "RAIDERS": "Las Vegas Raiders",
    "CHARGERS": "Los Angeles Chargers",
    "RAMS": "Los Angeles Rams",
    "DOLPHINS": "Miami Dolphins",
    "VIKINGS": "Minnesota Vikings",
    "PATRIOTS": "New England Patriots",
    "SAINTS": "New Orleans Saints",
    "GIANTS": "New York Giants",
    "JETS": "New York Jets",
    "EAGLES": "Philadelphia Eagles",
    "STEELERS": "Pittsburgh Steelers",
    "49ERS": "San Francisco 49ers",
    "SEAHAWKS": "Seattle Seahawks",
    "BUCS": "Tampa Bay Buccaneers",
    "BUCCANEERS": "Tampa Bay Buccaneers",
    "TITANS": "Tennessee Titans",
    "COMMANDERS": "Washington Commanders",
}

TEAM_CODES = frozenset(TEAM_NAMES)


class IntakeError(ValueError):
    """A source or validation failure that must stop the stage."""


@dataclass(frozen=True)
class SourceFile:
    kind: str
    contest: str
    url: str
    sha256: str
    bytes: int
    pages: int


@dataclass(frozen=True)
class Standing:
    place: int
    tied: bool
    alias: str
    record: str
    points: float
    page: int


@dataclass(frozen=True)
class Pick:
    team: str
    line: float


@dataclass(frozen=True)
class Entry:
    contest: str
    place: int
    tied: bool
    alias: str
    record: str
    picks: Tuple[Pick, ...]
    standings_page: int
    selections_page: int
    entry_identifier: str


def pdf_pages(data: bytes, *, layout: bool = False) -> List[str]:
    if not data.startswith(b"%PDF"):
        raise IntakeError("source is not a PDF")
    reader = PdfReader(BytesIO(data))
    pages = [
        (page.extract_text(extraction_mode="layout") if layout else page.extract_text()) or ""
        for page in reader.pages
    ]
    if not pages or not any(page.strip() for page in pages):
        raise IntakeError("PDF contains no extractable text")
    return pages


_STANDING_RE = re.compile(
    # Some Circa PDFs collapse the place into the alias (``1TPARLAYSAM``) and
    # the cancelled count into the points column (``20-4-1-020.50``).  The
    # numeric picks column, when present, is the stable delimiter for the alias.
    r"^\s*(\d+)(T?)\s*(.+?)\s+(?:(\d+)\s+)?"
    # Points are printed with exactly two decimals.  Make cancellations
    # non-greedy so collapsed text such as ``20-4-1-020.50`` becomes
    # cancellations=0, points=20.50 rather than cancellations=02.
    r"(\d+)-(\d+)-(\d+)-(\d+?)\s*(\d+\.\d{2})\s*$"
)


def parse_leading_standings(pages: Sequence[str], target: int = 3) -> List[Standing]:
    """Read whole place groups until at least ``target`` entries are included."""
    rows: List[Standing] = []
    for page_number, body in enumerate(pages, 1):
        for line in body.splitlines():
            match = _STANDING_RE.match(line)
            if not match:
                continue
            place, tied, alias, _picks, wins, losses, pushes, cancels, points = match.groups()
            alias = _clean_space(alias)
            rows.append(
                Standing(
                    place=int(place),
                    tied=bool(tied),
                    alias=alias,
                    record=f"{wins}-{losses}-{pushes}-{cancels}",
                    points=float(points),
                    page=page_number,
                )
            )

    if not rows:
        raise IntakeError("standings parser found no standings rows")

    leaders: List[Standing] = []
    index = 0
    last_place = -1
    while index < len(rows) and len(leaders) < target:
        place = rows[index].place
        if place < last_place:
            raise IntakeError("standings places are not non-decreasing")
        group: List[Standing] = []
        while index < len(rows) and rows[index].place == place:
            group.append(rows[index])
            index += 1
        leaders.extend(group)
        last_place = place

    if len(leaders) < target:
        raise IntakeError(f"standings contain only {len(leaders)} leading entries; expected at least {target}")
    aliases = [_alias_key(row.alias) for row in leaders]
    if len(aliases) != len(set(aliases)):
        raise IntakeError("leading standings contain a duplicate alias")
    return leaders


def parse_westgate_selections(
    pages: Sequence[str], leaders: Sequence[Standing]
) -> Dict[str, Tuple[Tuple[str, ...], int]]:
    wanted = {_alias_key(row.alias): row.alias for row in leaders}
    found: Dict[str, Tuple[Tuple[str, ...], int]] = {}
    for page_number, body in enumerate(pages, 1):
        for line in body.splitlines():
            tokens = line.split()
            if len(tokens) < 6:
                continue
            picks = tuple(tokens[-5:])
            if not all(token in TEAM_CODES for token in picks):
                continue
            alias = _clean_space(" ".join(tokens[:-5]))
            key = _alias_key(alias)
            if key not in wanted:
                continue
            if key in found:
                raise IntakeError(f"Westgate selections contain duplicate rows for {wanted[key]}")
            found[key] = (picks, page_number)
    _require_all_leaders("Westgate", wanted, found)
    return found


_CIRCA_PICK_RE = re.compile(
    r"(?<!\d)(\d+)\.\s+([A-Z0-9]+)\s+(PK|[+-]\d+(?:\.\d+|½)?)"
)


def parse_circa_selections(
    pages: Sequence[str], leaders: Sequence[Standing]
) -> Tuple[Dict[str, Tuple[Tuple[Tuple[int, str, float], ...], int]], Dict[str, float]]:
    wanted = {_alias_key(row.alias): row.alias for row in leaders}
    found: Dict[str, Tuple[Tuple[Tuple[int, str, float], ...], int]] = {}
    numbered: Dict[int, Tuple[str, float]] = {}

    for page_number, body in enumerate(pages, 1):
        for line in body.splitlines():
            raw_matches = list(_CIRCA_PICK_RE.finditer(line))
            if len(raw_matches) < 5:
                continue
            # Aliases may themselves contain date-like text such as
            # ``4-13-2029``.  In the PDF that can look like a numbered pick.
            # The official entry row ends with exactly five picks, so only the
            # final five matches are evidence.  The PDF usually orders them by
            # card number, but a handful of official rows do not; uniqueness
            # and the cross-row number/team/line map are the safe invariants.
            matches = raw_matches[-5:]
            numbers = [int(match.group(1)) for match in matches]
            if len(set(numbers)) != 5 or not all(1 <= number <= 28 for number in numbers):
                raise IntakeError(f"Circa entry row has invalid pick numbering: {line.strip()}")
            for match in matches:
                number = int(match.group(1))
                code = match.group(2)
                if code not in TEAM_CODES:
                    raise IntakeError(f"Circa selections contain unknown team code {code}")
                value = _line_number(match.group(3))
                prior = numbered.get(number)
                if prior and prior != (code, value):
                    raise IntakeError(
                        f"Circa selection number {number} maps inconsistently: {prior} versus {(code, value)}"
                    )
                numbered[number] = (code, value)

            alias = _clean_space(line[: matches[0].start()])
            key = _alias_key(alias)
            if key not in wanted:
                continue
            if key in found:
                raise IntakeError(f"Circa selections contain duplicate rows for {wanted[key]}")
            found[key] = (
                tuple((int(m.group(1)), m.group(2), _line_number(m.group(3))) for m in matches),
                page_number,
            )

    _require_all_leaders("Circa", wanted, found)
    _validate_numbered_card(numbered)
    line_map = {TEAM_NAMES[code]: value for code, value in numbered.values()}
    return found, line_map


_WG_CARD_RE = re.compile(
    r"^\s*(\d+)\s+([A-Z0-9]+)\*?.*?\s+(\d+)\s+([A-Z0-9]+)\*?\s+"
    r"(PK|[+-]\d+(?:\.\d+)?)\s*$"
)


def parse_westgate_card(pages: Sequence[str]) -> Tuple[Dict[str, float], List[Tuple[int, str, str]]]:
    games: List[Tuple[int, str, str]] = []
    line_map: Dict[str, float] = {}
    seen_numbers: set[int] = set()
    for body in pages:
        for line in body.splitlines():
            match = _WG_CARD_RE.match(line)
            if not match:
                continue
            n1, code1, n2, code2, raw_line2 = match.groups()
            if code1 not in TEAM_CODES or code2 not in TEAM_CODES:
                raise IntakeError(f"Westgate card contains unknown team code in line: {line.strip()}")
            number1, number2 = int(n1), int(n2)
            if number2 != number1 + 1 or number1 % 2 != 1:
                raise IntakeError(f"Westgate card has an invalid matchup numbering: {number1}/{number2}")
            if number1 in seen_numbers or number2 in seen_numbers:
                raise IntakeError(f"Westgate card repeats a selection number: {number1}/{number2}")
            seen_numbers.update((number1, number2))
            line2 = _line_number(raw_line2)
            line1 = -line2 if line2 else 0.0
            team1, team2 = TEAM_NAMES[code1], TEAM_NAMES[code2]
            line_map[team1] = line1
            line_map[team2] = line2
            games.append(((number1 + 1) // 2, team1, team2))

    if seen_numbers != set(range(1, 29)):
        missing = sorted(set(range(1, 29)) - seen_numbers)
        extra = sorted(seen_numbers - set(range(1, 29)))
        raise IntakeError(f"Westgate card must contain selection numbers 1-28; missing={missing}, extra={extra}")
    if len(line_map) != 28 or len(games) != 14:
        raise IntakeError("Westgate card did not produce 14 games and 28 unique teams")
    return line_map, games


def build_bundle(
    *,
    season: int,
    week: int,
    westgate_standings: bytes,
    westgate_selections: bytes,
    westgate_card: bytes,
    circa_standings: bytes,
    circa_selections: bytes,
    urls: Mapping[str, str],
    generated_at_utc: str,
) -> dict:
    if not (1 <= int(week) <= 18):
        raise IntakeError("week must be between 1 and 18")
    if int(week) == 1:
        raise IntakeError("Week 1 needs a pre-season cutoff source and is outside this automated path")

    raw = {
        "westgate_standings": westgate_standings,
        "westgate_selections": westgate_selections,
        "westgate_card": westgate_card,
        "circa_standings": circa_standings,
        "circa_selections": circa_selections,
    }
    pages = {
        name: pdf_pages(data, layout=(name == "circa_selections"))
        for name, data in raw.items()
    }

    wg_leaders = parse_leading_standings(pages["westgate_standings"])
    circa_leaders = parse_leading_standings(pages["circa_standings"])
    wg_rows = parse_westgate_selections(pages["westgate_selections"], wg_leaders)
    circa_rows, circa_lines = parse_circa_selections(pages["circa_selections"], circa_leaders)
    wg_lines, games = parse_westgate_card(pages["westgate_card"])

    if set(wg_lines) != set(circa_lines):
        missing_circa = sorted(set(wg_lines) - set(circa_lines))
        extra_circa = sorted(set(circa_lines) - set(wg_lines))
        raise IntakeError(
            f"contest cards describe different team pools; missing_in_circa={missing_circa}, extra_in_circa={extra_circa}"
        )

    entries: List[Entry] = []
    for standing in wg_leaders:
        codes, selection_page = wg_rows[_alias_key(standing.alias)]
        picks = tuple(Pick(TEAM_NAMES[code], wg_lines[TEAM_NAMES[code]]) for code in codes)
        entries.append(_entry("Westgate", season, week, standing, picks, selection_page))
    for standing in circa_leaders:
        pick_rows, selection_page = circa_rows[_alias_key(standing.alias)]
        picks = tuple(Pick(TEAM_NAMES[code], line) for _number, code, line in pick_rows)
        entries.append(_entry("Circa", season, week, standing, picks, selection_page))

    source_kinds = [
        ("westgate_standings", "Westgate"),
        ("westgate_selections", "Westgate"),
        ("westgate_card", "Westgate"),
        ("circa_standings", "Circa"),
        ("circa_selections", "Circa"),
    ]
    sources = [
        SourceFile(
            kind=kind,
            contest=contest,
            url=urls[kind],
            sha256=sha256(raw[kind]).hexdigest(),
            bytes=len(raw[kind]),
            pages=len(pages[kind]),
        )
        for kind, contest in source_kinds
    ]

    line_rows = [
        {
            "game": game,
            "officialTeam": team,
            "westgateCardLine": wg_lines[team],
            "circaCardLine": circa_lines[team],
        }
        for game, team1, team2 in games
        for team in (team1, team2)
    ]

    contest_rows = []
    for entry in entries:
        contest_rows.append(
            {
                "contest": entry.contest,
                "sourcePlace": entry.place,
                "alias": entry.alias,
                "record": entry.record,
                "ownerNotes": "Automated staging only; official PDFs parsed and cross-checked; owner approval required.",
                "picks": [pick.team for pick in entry.picks],
                "cardLines": [pick.line for pick in entry.picks],
                "entryIdentifier": entry.entry_identifier,
                "sourceReference": _source_reference(entry, urls),
                "sourceVerified": "Automated checks passed; owner approval pending",
                "expectedTieSize": _tie_size(entry, entries),
                "season": season,
                "week": week,
            }
        )

    bundle = {
        "schemaVersion": "cyrus-intake-stage-1",
        "generatedAtUtc": generated_at_utc,
        "season": int(season),
        "week": int(week),
        "status": "STAGED_NOT_LOADED",
        "sources": [asdict(source) for source in sources],
        "contestDataRows": contest_rows,
        "lineRows": line_rows,
        "validation": {
            "westgateLeaderEntries": len(wg_leaders),
            "circaLeaderEntries": len(circa_leaders),
            "picksPerEntry": 5,
            "westgateSelections": len(wg_leaders) * 5,
            "circaSelections": len(circa_leaders) * 5,
            "games": 14,
            "teams": 28,
            "sourceFiles": 5,
        },
    }
    canonical = json.dumps(bundle, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    bundle["bundleSha256"] = sha256(canonical.encode("utf-8")).hexdigest()
    return bundle


def _entry(
    contest: str,
    season: int,
    week: int,
    standing: Standing,
    picks: Tuple[Pick, ...],
    selection_page: int,
) -> Entry:
    if len(picks) != 5 or len({pick.team for pick in picks}) != 5:
        raise IntakeError(f"{contest} entry {standing.alias} must contain five distinct picks")
    identifier = str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"cyrus:{season}:{week}:{contest}:{_alias_key(standing.alias)}")
    )
    return Entry(
        contest=contest,
        place=standing.place,
        tied=standing.tied,
        alias=standing.alias,
        record=standing.record,
        picks=picks,
        standings_page=standing.page,
        selections_page=selection_page,
        entry_identifier=identifier,
    )


def _source_reference(entry: Entry, urls: Mapping[str, str]) -> str:
    prefix = "westgate" if entry.contest == "Westgate" else "circa"
    return (
        f"{urls[prefix + '_standings']} p{entry.standings_page}; "
        f"{urls[prefix + '_selections']} p{entry.selections_page}"
    )


def _tie_size(entry: Entry, entries: Sequence[Entry]) -> int | None:
    if not entry.tied:
        return None
    return sum(1 for other in entries if other.contest == entry.contest and other.place == entry.place)


def _validate_numbered_card(numbered: Mapping[int, Tuple[str, float]]) -> None:
    expected = set(range(1, 29))
    if set(numbered) != expected:
        missing = sorted(expected - set(numbered))
        extra = sorted(set(numbered) - expected)
        raise IntakeError(f"Circa selections must expose card numbers 1-28; missing={missing}, extra={extra}")
    teams = [numbered[number][0] for number in sorted(numbered)]
    if len(teams) != len(set(teams)):
        raise IntakeError("Circa card numbers do not map to 28 unique teams")
    for first in range(1, 29, 2):
        line1, line2 = numbered[first][1], numbered[first + 1][1]
        if abs(line1 + line2) > 1e-9:
            raise IntakeError(f"Circa matchup {first}/{first + 1} has non-opposite lines {line1}/{line2}")


def _require_all_leaders(label: str, wanted: Mapping[str, str], found: Mapping[str, object]) -> None:
    missing = [alias for key, alias in wanted.items() if key not in found]
    if missing:
        raise IntakeError(f"{label} selections are missing leading entry rows: {missing}")


def _line_number(value: str) -> float:
    value = value.replace("½", ".5")
    return 0.0 if value == "PK" else float(value)


def _clean_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _alias_key(value: str) -> str:
    value = _clean_space(value).upper()
    value = re.sub(r"\s+-\s+(\d+)$", r"-\1", value)
    # Circa uses outlined/display fonts that pypdf may expose as internal
    # spaces (for example ``WIL D  TER PS-1``).  Whitespace is formatting,
    # not identity, for the cross-PDF join.  Duplicate-key checks still make
    # a collision fail closed rather than silently choosing an entry.
    return re.sub(r"\s+", "", value)

