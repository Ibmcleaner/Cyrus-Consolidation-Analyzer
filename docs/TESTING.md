# Testing and reproducibility

```bash
python -m unittest discover -s tests -v
```

Packaging verification: **33 discovered, 26 passed, 7 skipped** using Python 3.12 and requirements pinned to the uploaded deployment versions. Eight new tests cover synthetic bundle/ties, agreement counts, missing leaders, timestamp-sensitive hashes, non-PDF rejection, Saturday date boundaries, Saturday route calculation, and both refusal logs.

The earlier private Cloud Shell run reported 25 passes with actual archived PDFs. That is separate evidence: this packaging session did not receive those PDFs. Do not describe all 33 as verified against real documents.

## Optional historical parser tests

Set `CYRUS_FIXTURE_DIR` to an absolute directory containing the exact verified fixtures:

- `2026 SuperContest Standings Week 5.pdf`
- `2026 SUPERCONTEST SELECTIONS WEEK 6.pdf`
- `2026 SUPERCONTEST GAME SHEET WK 6.pdf`
- `Circa-Sports-Million-VIII-Full-Season-Standings-After-Week-5.pdf`
- `Circa-Sports-Million-VIII-Week-6-Selections.pdf`

```bash
CYRUS_FIXTURE_DIR=/absolute/path/to/private-fixtures python -m unittest discover -s tests -v
```

Without the variable, seven tests explicitly skip. With it set, missing/wrong files fail. Keep fixtures outside source control and establish permissions and provenance. This runner does not automatically download PDFs or verify an external hash manifest.

Live requests, real PDF layout extraction, cloud storage writes, IAM, container build/startup, deployment, and Apps Script import were not run during packaging. Offline tests are not substitutes for these gates.
