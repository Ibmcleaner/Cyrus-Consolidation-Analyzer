# Offline demonstration

After installing requirements in Python 3.12, run from the repository root:

```bash
python -m examples.offline_demo
```

Open `demo-output/sample-report.html` locally and inspect `demo-output/sample-output.json`. Running again replaces these two generated files only. No source website, Google authentication, or cloud storage is used.

## Real versus mocked

Synthetic extracted text represents five source categories. Only `parser.pdf_pages` is mocked. The real standings, selections, card, cross-source validation, tie handling, identifier creation, and bundle builder run. Removing a required leader selection must raise `IntakeError`.

The invented dataset has four leader entries per group, complete ties, five picks per entry, and 28 card teams. Extra non-leading Circa rows supply the full card number mapping.

- No PDFs are generated or extracted.
- Source hashes describe synthetic text bytes, not official PDFs.
- URLs use `example.invalid`; they are illustrative, not source authenticity evidence.
- Inherited bundle labels such as `sourceVerified` are application output, not independent verification of real sources. The enclosing JSON marks `demoOnly` and `pdfExtractionMocked`.
- Agreement tables are a new demonstration, not the private board.
- Counts are not predictions, probabilities, or independent-person votes.

## Walkthrough

Show the source categories in `synthetic_sources()`, inspect preserved tie groups and evidence fields in JSON, open the source-separated agreement tables, and demonstrate the deliberate refusal. Explain which adapters and rules would change for a customer use case.
