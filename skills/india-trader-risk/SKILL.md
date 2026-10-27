---
name: india-trader-risk
description: Check INR equity proposals against current account, quote, session, instrument and intraday risk constraints.
---

Read ../../docs/schemas.md and ../../docs/operations.md. Run `risk`; exit 1 indicates blocked proposals, 2 invalid inputs. Inputs need a reconciled dated account, timestamped quotes, same-day instrument metadata and verified calendar. Explain every BLOCK; do not silently loosen limits, relabel delayed quotes as live or substitute cost basis for a current valuation. Checks include ticks/circuits, whole shares, fees, cumulative cash/position exposure, duplicate orders, daily loss and entry cutoff. No sale is assumed filled to finance a buy. Every changed order, account or data input invalidates prior approval.

Use this skill only for the requested Indian-market task. Work from the repository root or run the bundled launcher by its absolute path. Python 3.10+ and the standard library are sufficient.

Run `python <skill-folder>/scripts/run.py --help` to see all commands. Global options `--workspace PATH`, `--now TIMESTAMP` and `--out PATH` precede the command. The graphical application exposes these services without terminal commands; see ../../docs/ui.md. The default CLI workspace is `trader/` under the working directory. `--now` is for explicit offline simulation only; omit for current checks. The launcher resolves the shared engine relative to this repository; keep the full repository together.

All trade plans are paper proposals. Free data can be delayed, blocked or incomplete. Keep source timestamps and evidence, distinguish observed data from inference, and never fill missing facts with invented values. See [sources](../../docs/sources.md), [schemas](../../docs/schemas.md), and [operations](../../docs/operations.md).
