---
name: india-trader-disclosures
description: Track public Indian promoter and insider disclosures, including transaction and disclosure dates.
---

This replaces the upstream US politician tracker. It does not track Indian MPs' stock trades. Read ../../docs/sources.md and ../../docs/schemas.md. `filings insider NSE:INFY` fetches public raw metadata. Normalize exchange CSV or attached filings to the disclosure schema, preserve source_url, transaction_date, disclosed_at and transaction_type, then `disclosures INPUT`. The command records seen IDs. Keep gifts, pledges, ESOPs and inter-se transfers distinct from market purchases. Do not infer unpublished holdings or treat reported activity as inside information.

Use this skill only for the requested Indian-market task. Work from the repository root or run the bundled launcher by its absolute path. Python 3.10+ and the standard library are sufficient.

Run `python <skill-folder>/scripts/run.py --help` to see all commands. Global options `--workspace PATH`, `--now TIMESTAMP` and `--out PATH` precede the command. The graphical application exposes these services without terminal commands; see ../../docs/ui.md. The default CLI workspace is `trader/` under the working directory. `--now` is for explicit offline simulation only; omit for current checks. The launcher resolves the shared engine relative to this repository; keep the full repository together.

All trade plans are paper proposals. Free data can be delayed, blocked or incomplete. Keep source timestamps and evidence, distinguish observed data from inference, and never fill missing facts with invented values. See [sources](../../docs/sources.md), [schemas](../../docs/schemas.md), and [operations](../../docs/operations.md).
