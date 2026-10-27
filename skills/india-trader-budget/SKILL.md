---
name: india-trader-budget
description: Size INR whole-share delivery allocations and fully funded long intraday trades with stop-based risk limits.
---

Read ../../docs/schemas.md. Confirm the user's capital and risk limits; examples are synthetic. `budget` uses targets.json, prices.json and config.json and writes orders.json. For existing holdings use rebalance. `intraday NSE:INFY --entry 1500 --stop 1480` sizes a long MIS proposal with round-trip estimated charges. No fractional shares, notional tickets or assumed 5x leverage. Stop loss is planning metadata only; no linked exit is placed. Send all proposals through risk.

Use this skill only for the requested Indian-market task. Work from the repository root or run the bundled launcher by its absolute path. Python 3.10+ and the standard library are sufficient.

Run `python <skill-folder>/scripts/run.py --help` to see all commands. Global options `--workspace PATH`, `--now TIMESTAMP` and `--out PATH` precede the command. The graphical application exposes these services without terminal commands; see ../../docs/ui.md. The default CLI workspace is `trader/` under the working directory. `--now` is for explicit offline simulation only; omit for current checks. The launcher resolves the shared engine relative to this repository; keep the full repository together.

All trade plans are paper proposals. Free data can be delayed, blocked or incomplete. Keep source timestamps and evidence, distinguish observed data from inference, and never fill missing facts with invented values. See [sources](../../docs/sources.md), [schemas](../../docs/schemas.md), and [operations](../../docs/operations.md).
