---
name: india-trader-screener
description: Screen and rank Indian equity research metrics using user-defined numerical rules.
---

Use `screen --input METRICS --rules RULES` or workspace metrics.json/rules.json. Read ../../docs/schemas.md. Missing rule metrics fail explicitly. Explain failed rules and missing ranking metrics. Compare one reporting basis and period per company; do not rank duplicate standalone/consolidated rows together. Screen results are candidates, not orders. For intraday candidates also review liquidity, spread, surveillance, broker eligibility and current instrument metadata.

Use this skill only for the requested Indian-market task. Work from the repository root or run the bundled launcher by its absolute path. Python 3.10+ and the standard library are sufficient.

Run `python <skill-folder>/scripts/run.py --help` to see all commands. Global options `--workspace PATH`, `--now TIMESTAMP` and `--out PATH` precede the command. The graphical application exposes these services without terminal commands; see ../../docs/ui.md. The default CLI workspace is `trader/` under the working directory. `--now` is for explicit offline simulation only; omit for current checks. The launcher resolves the shared engine relative to this repository; keep the full repository together.

All trade plans are paper proposals. Free data can be delayed, blocked or incomplete. Keep source timestamps and evidence, distinguish observed data from inference, and never fill missing facts with invented values. See [sources](../../docs/sources.md), [schemas](../../docs/schemas.md), and [operations](../../docs/operations.md).
