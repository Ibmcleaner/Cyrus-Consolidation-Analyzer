"""Exercise real parser/bundle logic with synthetic extracted text, NOT PDF bytes.

Only the pdf_pages extraction boundary is mocked. No network or cloud calls.
The display/aggregation below is a new demo, not the private Apps Script board.
"""
from collections import Counter
import html
import json
from pathlib import Path
from unittest.mock import patch

from cyrus_intake import parser


def synthetic_sources():
    codes = list(dict.fromkeys(parser.TEAM_NAMES))[:28]
    standings = "\n".join([
        "1T SAMPLE-A 20-4-1-0 20.50", "1T SAMPLE-B 20-4-1-0 20.50",
        "3T SAMPLE-C 19-5-1-0 19.50", "3T SAMPLE-D 19-5-1-0 19.50",
    ])
    card = "\n".join(f"{n} {codes[n-1]} {n+1} {codes[n]} +3.0"
                     for n in range(1, 29, 2))
    wg = "\n".join(f"SAMPLE-{letter} " + " ".join(codes[start:start+5])
                    for letter, start in zip("ABCD", [0, 0, 2, 4]))
    def picks(indices):
        return " ".join(f"{i+1}. {codes[i]} {'-3.0' if i % 2 == 0 else '+3.0'}"
                        for i in indices)
    circa = [f"SAMPLE-{letter} " + picks(range(start, start+5))
             for letter, start in zip("ABCD", [0, 0, 2, 4])]
    # Extra non-leading rows expose the entire 28-team numbered card.
    for start in range(0, 28, 5):
        circa.append(f"SUPPORT-{start} " + picks([(start+i) % 28 for i in range(5)]))
    return {
        "westgate_standings": standings, "circa_standings": standings,
        "westgate_card": card, "westgate_selections": wg,
        "circa_selections": "\n".join(circa),
    }


def make_bundle(sources=None, timestamp="2026-10-27T12:00:00Z"):
    sources = synthetic_sources() if sources is None else sources
    raw = {name: value.encode("utf-8") for name, value in sources.items()}
    # These bytes are deliberately NOT represented as real source PDFs.
    with patch.object(parser, "pdf_pages", side_effect=lambda data, **kw: [data.decode("utf-8")]):
        bundle = parser.build_bundle(season=2026, week=8, **raw,
            urls={name: f"https://example.invalid/synthetic/{name}.txt" for name in raw},
            generated_at_utc=timestamp)
    return bundle


def agreement(bundle):
    groups = {}
    for contest in ("Westgate", "Circa"):
        entries = [r for r in bundle["contestDataRows"] if r["contest"] == contest]
        counts = Counter(team for row in entries for team in row["picks"])
        groups[contest] = {"entries": len(entries), "counts": dict(sorted(counts.items()))}
    return groups


def main():
    bundle = make_bundle()
    summary = agreement(bundle)
    altered = synthetic_sources()
    altered["westgate_selections"] = altered["westgate_selections"].replace("SAMPLE-A", "MISSING-A")
    try:
        make_bundle(altered)
    except parser.IntakeError as exc:
        refusal = str(exc)
    else:
        raise AssertionError("Expected the missing-entry example to refuse")
    report = {"demoOnly": True, "pdfExtractionMocked": True,
              "storageWritten": False, "bundle": bundle,
              "agreement": summary, "expectedRefusal": refusal}
    output = Path(__file__).resolve().parents[1] / "demo-output"
    output.mkdir(exist_ok=True)
    (output / "sample-output.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    tables = []
    for group, values in summary.items():
        rows = "".join(f"<tr><td>{html.escape(team)}</td><td>{count} / {values['entries']}</td></tr>"
                       for team, count in values["counts"].items())
        tables.append(f"<section><h2>{html.escape(group)}</h2><table><tr><th>Selection</th><th>Agreement</th></tr>{rows}</table></section>")
    page = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cyrus Consolidation Analyzer — Synthetic Demo</title>
<style>body{font:17px system-ui;background:#f3f6fa;color:#172b40;max-width:1000px;margin:40px auto;padding:20px}
section{background:white;padding:24px;margin:20px 0;border-radius:12px}td,th{text-align:left;padding:8px 24px 8px 0}
.notice{border-left:5px solid #a65a00;padding:16px;background:#fff4df}code{overflow-wrap:anywhere}</style>
<h1>Cyrus Consolidation Analyzer</h1><p>Offline validation and comparison demonstration</p>
<p class="notice">SYNTHETIC DATA — PDF extraction is mocked. No live sources, cloud writes, actual standings, or prediction claims.
This is a new demo display, not the private production board.</p>
<section><h2>Validation summary</h2><p>5 synthetic source categories · 8 entries · 14 matchups · 28 teams</p>
<p>Whole tie groups retained. Agreement counts entries, not independent people or forecast probabilities.</p></section>"""
    page += "".join(tables) + f"<section><h2>Deliberate failure example</h2><p>{html.escape(refusal)}</p><p>Incomplete data was refused.</p></section></html>"
    (output / "sample-report.html").write_text(page, encoding="utf-8")
    print(f"Synthetic demo complete: {output}")
    print("No network requests or cloud storage writes were made.")


if __name__ == "__main__":
    main()
