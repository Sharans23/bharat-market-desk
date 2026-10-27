---
name: india-trader-broker
description: Connect Kite, Dhan and Groww for account/data reads, preview tickets and simulate approved local paper fills.
---

Read ../../docs/operations.md and ../../docs/brokers.md. Use `connections connect kite` in the user's local terminal for hidden credential entry, then `connections status/sync/report kite`. Dhan and Groww use the same interface. Never request credentials in chat. Snapshots retain broker financial semantics and do not replace paper accounts or FIFO lots. `connections quotes kite NSE:INFY --publish` can replace paper quotes only after all symbols succeed; preserve timestamps. `connections preview PROVIDER` is FORMAT_ONLY, not risk approval. This implementation cannot submit live orders. `broker show` rechecks risk and renders the exact LIMIT DAY Kite-compatible manual payload. The user acknowledgement is `YES FULL_FINGERPRINT` for one order; pass the actual user response to `broker approve --index N --reply TEXT`. Never manufacture a reply from broad permission to build software. `broker fill --index N --fill-price PRICE` records a synthetic fill exactly at the approved limit; it is not evidence of market execution. Inputs and risk must still match; approvals expire and cannot replay. Stop-loss metadata is not a protective order. Live actions remain with the user in their broker application.

Use this skill only for the requested Indian-market task. Work from the repository root or run the bundled launcher by its absolute path. Python 3.10+ and the standard library are sufficient.

Run `python <skill-folder>/scripts/run.py --help` to see all commands. Global options `--workspace PATH`, `--now TIMESTAMP` and `--out PATH` precede the command. The graphical application exposes these services without terminal commands; see ../../docs/ui.md. The default CLI workspace is `trader/` under the working directory. `--now` is for explicit offline simulation only; omit for current checks. The launcher resolves the shared engine relative to this repository; keep the full repository together.

All trade plans are paper proposals. Free data can be delayed, blocked or incomplete. Keep source timestamps and evidence, distinguish observed data from inference, and never fill missing facts with invented values. See [sources](../../docs/sources.md), [schemas](../../docs/schemas.md), and [operations](../../docs/operations.md).
