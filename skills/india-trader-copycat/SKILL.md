---
name: india-trader-copycat
description: Reconstruct an Indian disclosed equity sleeve from fund holdings or valued investor disclosures; compare snapshots.
---

Use NSE/BSE shareholding disclosures or an AMC's published fund portfolio. Read ../../docs/sources.md and ../../docs/schemas.md. Import normalized rows with source URLs, snapshot date and market_value_inr or portfolio_weight_pct. Issuer ownership percentages cannot be treated as portfolio weights. Never claim a complete celebrity investor portfolio from thresholded issuer disclosures. Compare quantities only after checking splits, bonuses and mergers.

Commands: `copycat INPUT --top 5` writes targets; `copycat INPUT --previous OLD` compares quantities. The selected disclosed equity sleeve is renormalized; cash and omitted assets are not recovered.

Use this skill only for the requested Indian-market task. Work from the repository root or run the bundled launcher by its absolute path. Python 3.10+ and the standard library are sufficient.

Run `python <skill-folder>/scripts/run.py --help` to see all commands. Global options `--workspace PATH`, `--now TIMESTAMP` and `--out PATH` precede the command. The graphical application exposes these services without terminal commands; see ../../docs/ui.md. The default CLI workspace is `trader/` under the working directory. `--now` is for explicit offline simulation only; omit for current checks. The launcher resolves the shared engine relative to this repository; keep the full repository together.

All trade plans are paper proposals. Free data can be delayed, blocked or incomplete. Keep source timestamps and evidence, distinguish observed data from inference, and never fill missing facts with invented values. See [sources](../../docs/sources.md), [schemas](../../docs/schemas.md), and [operations](../../docs/operations.md).
