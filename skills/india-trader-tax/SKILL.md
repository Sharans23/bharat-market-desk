---
name: india-trader-tax
description: Compute Indian equity FIFO realized gains, financial-year totals and delivery loss candidates.
---

Read ../../docs/tax.md and ../../docs/schemas.md. `tax report --input LEDGER --fy 2026-27` requires all opening purchases and fills, with demat-account identity and actual delivery classification. `tax harvest` lists estimated delivery loss candidates but creates no orders. Same-day non-delivery trades can be speculative business even if tagged CNC. Delivery shares are assumed capital assets for the report; frequent trading may need a different treatment. No US wash-sale window or HIFO selection is imported. Do not describe totals as final tax liability.

Use this skill only for the requested Indian-market task. Work from the repository root or run the bundled launcher by its absolute path. Python 3.10+ and the standard library are sufficient.

Run `python <skill-folder>/scripts/run.py --help` to see all commands. Global options `--workspace PATH`, `--now TIMESTAMP` and `--out PATH` precede the command. The graphical application exposes these services without terminal commands; see ../../docs/ui.md. The default CLI workspace is `trader/` under the working directory. `--now` is for explicit offline simulation only; omit for current checks. The launcher resolves the shared engine relative to this repository; keep the full repository together.

All trade plans are paper proposals. Free data can be delayed, blocked or incomplete. Keep source timestamps and evidence, distinguish observed data from inference, and never fill missing facts with invented values. See [sources](../../docs/sources.md), [schemas](../../docs/schemas.md), and [operations](../../docs/operations.md).
