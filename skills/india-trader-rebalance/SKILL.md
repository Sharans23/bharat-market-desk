---
name: india-trader-rebalance
description: Plan INR whole-share delivery portfolio rebalancing against capped target weights.
---

Run `rebalance --band 5` after reconciling account holdings and quotes. Band is percentage points of total equity. It writes capped LIMIT proposals with drift details; it does not force fractional shares or spend unfilled sale proceeds. The plan includes exits of holdings omitted from the target, so explicitly show those exits. Intraday holdings must be closed/reconciled first. Sell first, record actual/paper fills, regenerate buys, rerun risk and obtain fresh per-ticket acknowledgement. Charges and caps can leave residual drift/cash.

Use this skill only for the requested Indian-market task. Work from the repository root or run the bundled launcher by its absolute path. Python 3.10+ and the standard library are sufficient.

Run `python <skill-folder>/scripts/run.py --help` to see all commands. Global options `--workspace PATH`, `--now TIMESTAMP` and `--out PATH` precede the command. The graphical application exposes these services without terminal commands; see ../../docs/ui.md. The default CLI workspace is `trader/` under the working directory. `--now` is for explicit offline simulation only; omit for current checks. The launcher resolves the shared engine relative to this repository; keep the full repository together.

All trade plans are paper proposals. Free data can be delayed, blocked or incomplete. Keep source timestamps and evidence, distinguish observed data from inference, and never fill missing facts with invented values. See [sources](../../docs/sources.md), [schemas](../../docs/schemas.md), and [operations](../../docs/operations.md).
