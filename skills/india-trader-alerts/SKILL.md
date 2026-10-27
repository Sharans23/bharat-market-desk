---
name: india-trader-alerts
description: Check Indian equity price levels, CAS-aware market sessions and intraday exit reminders.
---

Use `quote NSE:INFY` for unofficial research data and `clock --cas yes` for session state; missing CAS eligibility returns UNKNOWN. `alerts` performs one poll of workspace alerts.json, rejecting stale quotes and storing once-per-IST-date deduplication. Read ../../docs/operations.md. The open alert means the first poll observing the continuous session, not a guaranteed opening-bell delivery. Reminders do not close positions. Calendar coverage is bounded; verify later circulars and special sessions before use. A scheduler is an external user-configured operation.

Use this skill only for the requested Indian-market task. Work from the repository root or run the bundled launcher by its absolute path. Python 3.10+ and the standard library are sufficient.

Run `python <skill-folder>/scripts/run.py --help` to see all commands. Global options `--workspace PATH`, `--now TIMESTAMP` and `--out PATH` precede the command. The graphical application exposes these services without terminal commands; see ../../docs/ui.md. The default CLI workspace is `trader/` under the working directory. `--now` is for explicit offline simulation only; omit for current checks. The launcher resolves the shared engine relative to this repository; keep the full repository together.

All trade plans are paper proposals. Free data can be delayed, blocked or incomplete. Keep source timestamps and evidence, distinguish observed data from inference, and never fill missing facts with invented values. See [sources](../../docs/sources.md), [schemas](../../docs/schemas.md), and [operations](../../docs/operations.md).
