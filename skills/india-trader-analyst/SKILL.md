---
name: india-trader-analyst
description: Analyze Indian quarterly financial results with INR/lakh/crore unit conversion and comparable reporting periods.
---

Use `filings results NSE:INFY` to discover filings; read original results and normalize them to ../../docs/schemas.md. `analyst INPUT` writes metrics.json with revenue, PAT, net margin, YoY revenue growth and four-quarter EPS. Keep standalone and consolidated series separate. Accept individual quarters only; derive Q4 from audited year minus nine months only if scope and restatements match, documenting the derivation. Never label cumulative YTD as a quarter. Review banking/NBFC metrics separately; EPS must share a consistent corporate-action basis.

Use this skill only for the requested Indian-market task. Work from the repository root or run the bundled launcher by its absolute path. Python 3.10+ and the standard library are sufficient.

Run `python <skill-folder>/scripts/run.py --help` to see all commands. Global options `--workspace PATH`, `--now TIMESTAMP` and `--out PATH` precede the command. The graphical application exposes these services without terminal commands; see ../../docs/ui.md. The default CLI workspace is `trader/` under the working directory. `--now` is for explicit offline simulation only; omit for current checks. The launcher resolves the shared engine relative to this repository; keep the full repository together.

All trade plans are paper proposals. Free data can be delayed, blocked or incomplete. Keep source timestamps and evidence, distinguish observed data from inference, and never fill missing facts with invented values. See [sources](../../docs/sources.md), [schemas](../../docs/schemas.md), and [operations](../../docs/operations.md).
