# Operational behavior

## Research to paper trade

1. Create a workspace with `init` or supply your own schema-valid data. Replace all synthetic data for actual research. Set capital and risk limits deliberately.
2. Import a disclosed portfolio, analyze quarterly results, or create target weights. Check dates and source coverage.
3. Use `budget`, `intraday` or `rebalance` to create proposals. Planning may use older reference data, but proposals cannot become ready until current risk checks pass.
4. Reconcile cash, holdings, lots and daily P&L; refresh every held/proposed quote and verify today's instrument master. Omit `--now` for current time.
5. Run `risk` or `broker show`. Review all BLOCK reasons and each proposed ticket. PASS means only that configured checks passed, not that the trade is suitable or profitable.
6. For a local paper simulation, record the user's exact one-ticket response with `broker approve --index 1 --reply 'YES FULL_FINGERPRINT'`. Then `broker fill --index 1 --fill-price LIMIT_PRICE` records one simulated fill. Do not invent this acknowledgement from general permission to develop the project.
7. Refresh/recheck after every fill. Each changed account, order set, price input, config, instrument file, effective calendar or fee profile invalidates earlier approvals. This intentionally prevents approving a batch once and filling against a changed account.

`broker show` produces a Kite-compatible cash LIMIT DAY payload. This paper command does not send anything to Zerodha or request credentials. The separate `connections` commands authenticate Kite, Dhan or Groww for account/data reads; see [broker setup](brokers.md) for encrypted local credential storage, account snapshots and supported capabilities. A local paper approval is not authorization for a live order. Submit any real order yourself in your broker application after checking its current details, funds, protection and eligibility.

## Limits of the simulation

Paper fills occur only at the approved limit, on an explicit command. They do not model whether the order would have filled, queue priority, partial fills, spread, market impact, circuit locks, outages or broker rejection. Planned stops can be exceeded by gaps/slippage and are not automatically transmitted or enforced. Daily P&L needs reconciliation of unrealized movements; this is not a continuously running risk engine.

The engine is fully funded, long-only cash equity. A sell needs actual holdings in the same product; proposed buys do not create sellable stock. Proposed sells do not fund new buys or reduce concentration until filled. Exits remain possible after a daily-loss or entry-count halt, but still require correct quotes, active session and eligible instruments. Limits on order value can require a smaller exit; review that with the user's configured policy.

The quote age default is 60 seconds and risk/approval lifetime is 120 seconds. These are software settings, not exchange rules. Intraday entry cutoff 14:45 and exit reminder 15:00 are conservative user-configurable defaults; they are not claimed to be a broker's square-off schedule.

Fee estimates model one order per fill using the bundled illustrative Zerodha NSE cash profile. They are not contract-note accurate: per-scrip/day aggregation, final rounding, some investor tariffs and exceptional fees differ. Delivery classification must be reconciled for same-day CNC round trips. Do not use modeled charges as your tax input without review.

## Calendar coverage

The bundled IST clock covers the 2026 NSE cash holiday list and the August CAS regime through 6 December 2026. CAS-eligible equity stops continuous trading at 15:15 in that regime; other cash shares continue to 15:30. Auction periods are identified but unsupported for order readiness. Unknown CAS eligibility, BSE sessions, later calendar dates, unresolved Budget/Muhurat sessions and unverified special-session times return UNKNOWN. Follow [official NSE CAS information](https://www.nseindia.com/static/products-services/closing-auction-session) and later exchange circulars.

The further October SEBI notice is recorded in the source ledger, but its full linked detail could not be retrieved during this build. A hard boundary before the announced December transition avoids silently applying an old schedule. Future annual holidays and emergency closures require maintenance; a local calendar cannot discover them by itself.

## Polling and files

`news`, `disclosures` and `alerts` each run once and persist deduplication state. No Windows scheduled task or background process is installed. If you schedule these externally, use a single writer per workspace, preserve error logs and keep data refreshed. Do not schedule `approve` or `fill` as unattended trading actions.

Paper account updates use a process lock and atomically replace one account.json containing positions, cash, approvals and events. There is no separate event/portfolio partial commit. If a process crashes with `.account.lock` present, confirm the process has stopped before deleting that lock. Research-state files are atomic individual writes, but do not support simultaneous pollers. This is a local trusted-file workflow; hashes detect accidental changes, not a malicious operator editing both inputs and approvals.

`init` never overwrites a nonempty workspace. Planning commands intentionally replace `orders.json`; `quote` replaces the requested quote snapshot. Keep backups of user records. The development live probe writes only `docs/live-probe.json` and performs public reads.
