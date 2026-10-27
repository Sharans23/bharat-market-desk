---
name: india-trader-news
description: Monitor public Indian company announcements and India-focused news for a watchlist.
---

Read ../../docs/sources.md. Use `news NSE:INFY NSE:TCS` for RSS and `filings announcements NSE:INFY` for exchange metadata. `news --input FILE` accepts a saved normalized feed. Verify material claims against the original exchange filing and separate publication time, event date and fetch time. A headline is not an automatic trade signal. Errors and unknown dates must remain visible. Run once per requested poll; no scheduler is installed.

Use this skill only for the requested Indian-market task. Work from the repository root or run the bundled launcher by its absolute path. Python 3.10+ and the standard library are sufficient.

Run `python <skill-folder>/scripts/run.py --help` to see all commands. Global options `--workspace PATH`, `--now TIMESTAMP` and `--out PATH` precede the command. The graphical application exposes these services without terminal commands; see ../../docs/ui.md. The default CLI workspace is `trader/` under the working directory. `--now` is for explicit offline simulation only; omit for current checks. The launcher resolves the shared engine relative to this repository; keep the full repository together.

All trade plans are paper proposals. Free data can be delayed, blocked or incomplete. Keep source timestamps and evidence, distinguish observed data from inference, and never fill missing facts with invented values. See [sources](../../docs/sources.md), [schemas](../../docs/schemas.md), and [operations](../../docs/operations.md).
