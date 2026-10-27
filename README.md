# Cyrus Consolidation Analyzer

### Multi-Source Data & Decision Workflow Engine

**Gather information. Validate it. Compare it. Make exceptions visible.**

Cyrus Consolidation Analyzer demonstrates how a recurring document-driven task can become a traceable automation workflow. Its first pilot uses sports contest documents—a domain the founder knew well enough to evaluate the output. The broader focus is business automation, not a company limited to sports-related tools.

**Owner:** Robert Legorreta  
**Status:** Private pilot; public source showcase and offline synthetic demo  
**Checkpoint:** October 27, 2026

## Explore the project

- [Architecture and code walkthrough](docs/ARCHITECTURE.md)
- [Offline demo instructions](docs/DEMO.md)
- [Sample JSON output](demo-output/sample-output.json)
- [Sample HTML report](demo-output/sample-report.html) — download and open locally; GitHub displays its source rather than hosting a live page
- [Engineering case study: problems, fixes, and lessons](docs/ENGINEERING_CASE_STUDY.md)
- [Testing and historical fixtures](docs/TESTING.md)
- [Security and known limitations](docs/SECURITY_AND_LIMITATIONS.md)

## Business applications

The reusable pattern is **collect → standardize → validate → consolidate → compare → review → deliver**. The current parsers are specialized, not a universal connector framework. Other uses require customer-specific integrations, schemas, and rules.

| Potential adaptation | Value | New work required |
| --- | --- | --- |
| Supplier comparison | Compare quotes, terms, and delivery commitments | Quote extraction, supplier identity, currency/unit rules |
| Invoice review | Surface invoice/PO/receipt discrepancies | Accounting connectors, matching and approval rules |
| Inventory reconciliation | Flag inconsistent counts and stale records | SKU mapping, feeds, freshness thresholds |
| Operations reporting | Assemble period-specific reports and exceptions | System connectors, status definitions, ownership rules |
| Compliance evidence tracking | Flag missing or expired evidence | Retention/access controls and qualified domain review |
| Customer feedback analysis | Display recurring themes with evidence | Classification, privacy controls, deduplication and evaluation |

These are adaptation opportunities—not implemented production integrations. No customer ROI or time-savings metric is claimed.

## Included in this package

Actual Python application source, original tests, Dockerfile, pinned direct dependencies, an offline synthetic demo, eight new tests, and engineering documentation. The received application runtime files are unchanged.

The private Google Sheets/Apps Script board is **not included**. Its import and consensus display are separate from the intake service. The included HTML report is a new illustrative display—not a copy of the private board.

## Quick start

Requires Python 3.12. Run from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m examples.offline_demo
```

On Windows PowerShell, create the environment with `py -3.12 -m venv .venv` and activate with `.venv\Scripts\Activate.ps1`. The remaining `python` commands are the same. Windows activation was not tested during packaging.

Open `demo-output/sample-report.html` locally. The demo rewrites only its JSON and HTML output files. It performs no network fetches or cloud writes.

**Demo boundary:** PDF extraction is mocked using invented extracted text. Real record parsing, tie handling, cross-source validation, and bundle construction run. This does not demonstrate real-PDF extraction, cloud permissions, or live scheduling.

## Evidence

| Check | Result |
| --- | --- |
| Original private pilot with archived PDFs and pinned direct dependencies | 25 tests passed in owner-provided Cloud Shell evidence |
| This public package, local Python 3.12 | 33 discovered: **26 passed, 7 explicitly skipped** |
| Synthetic offline demo | Completed; sample outputs generated and deliberate missing-entry refusal verified |

Seven historical tests require PDFs not redistributed here. Skipped tests are not passed tests. See [fixture instructions](docs/TESTING.md).

## Current pilot implementation

This private Cloud Run service discovers the official Westgate SuperContest and
Circa Million weekly PDFs, validates them as one coherent week, and optionally
stores a create-only evidence bundle in a private staging bucket. Link-label matching is not complete document-content season/week verification; see the limitations below.

It **does not connect to Google Sheets and cannot load C1**.  A later, separately
reviewed approval step will compare a staged bundle to the owner board before
any workbook write is considered.

## Endpoints

- `GET /health`
- `POST /run?season=2026&week=6&write=false` — live dry run, no storage writes
- `POST /run?season=2026&week=6&write=true` — immutable private staging write
- `POST /scheduled` — determine the configured current NFL week and write one
  immutable private staging bundle; intended only for authenticated Cloud
  Scheduler calls

The service must remain private.  `STAGING_BUCKET` identifies the private bucket
used only when `write=true`.

The scheduled route requires `SCHEDULE_SEASON`, `SCHEDULE_WEEK1_DATE` (ISO
date), and `SCHEDULE_TIMEZONE`. It automates only Weeks 2-18 and returns a
successful no-write skip outside that range. The scheduler never connects to
Google Sheets; owner preview and approval remain separate.

## Fail-closed checks

- link-label matching for current-week card/selections and prior-week standings (content-level period verification remains incomplete)
- whole standings tie groups through the top three entries
- exactly five distinct picks per selected entry
- exactly 14 matchups / 28 unique teams per contest
- matching Westgate and Circa team pools
- stable number/team/line mapping across every Circa entry row
- opposite lines within every matchup
- official final download hosts only
- Circa PDF links discovered from either embedded links or visible tweet text
- official PDF paths safely encode literal spaces before network requests
- deterministic bundle hash for identical inputs including timestamp, and create-only storage objects

## Important limits and next steps

The exact original Week 7 failure is unresolved. Week 8 end-to-end acceptance remains open. The runtime assumes 14 games, relies on rolling source pages, lacks full PDF-content period checks, and uses sequential rather than transactional storage writes. Authentication is supplied by Cloud Run IAM, not Flask middleware. Read [the full limitations](docs/SECURITY_AND_LIMITATIONS.md) before operational use.

For a local health-only check, use `python -m flask --app app run --host 127.0.0.1` and visit `http://127.0.0.1:5000/health`. Do not expose the development server publicly. Other routes may access live sources and cloud storage; use the offline demo for a credential-free example.

## Ownership and publication

Owner-directed, AI-assisted engineering: the owner executed the private cloud commands and supplied observed outputs; AI assistance supported diagnostics, review, tests, and documentation. This is not a claim of autonomous development or production certification.

Source inspection and pattern checks found no credentials or live account-specific resource identifiers in the supplied archive. This was not a formal security audit. Historical tests retain contest-entry aliases and assertions; demo aliases are invented. Private PDFs and credentials are excluded. No code license has been selected; third-party data rights remain separate.
