# Files and input schemas

All money is INR. All JSON numeric values must be finite; quantities are positive integers unless a schema explicitly allows zero. Prices have per-instrument tick sizes. Use `NSE:INFY` or `BSE:500209` identities; `.NS` is a Yahoo provider suffix, not the internal symbol. Indian grouping such as `1,00,000` is accepted by numeric import readers. Do not use percentages with a `%` suffix: use numeric percentage points.

Global CLI options precede the command: `python -m india_trader --workspace PATH --now TIMESTAMP --out FILE COMMAND ...`. Timestamps require timezone, normally `+05:30`. Output is JSON. Exit codes: 0 success, 1 risk block/provider or alert partial errors, 2 invalid input or unavailable source. A screen with zero passing companies is a successful query, not an execution error.

## Workspace

| File | Meaning |
| --- | --- |
| `config.json` | Capital and risk settings; default template in `data/default-config.json` |
| `account.json` | Atomic combined portfolio, paper event log and outstanding approvals |
| `prices.json` | Timestamped INR quotes, each with source |
| `instruments.json` | Same-day verified eligibility, series, ticks, bands and broker identity |
| `targets.json` | Target equity-sleeve weights |
| `orders.json` | Latest proposal; sizing/rebalancing replace it |
| `risk.json` | Exact order fingerprints and entire-input context hash |
| `metrics.json`, `rules.json`, `shortlist.json` | Analyst output, screener rules and results |
| `alerts.json`, `alerts-state.json` | Polling rules and fired IDs |
| `news-state.json`, `disclosures-state.json` | Seen item IDs |
| `calendar.json` | Optional verified override for bundled calendar |

`account.json` shape:

```json
{
  "portfolio": {
    "currency": "INR", "cash_inr": 100000,
    "trading_date": "2026-10-26", "daily_pnl_inr": 0,
    "day_start_equity_inr": 100000, "day_net_cash_flow_inr": 0,
    "positions": [], "lots": []
  },
  "events": [], "approvals": {}
}
```

Position: `{"symbol":"NSE:INFY","product":"CNC","quantity":10}`. Cost lot: `{"symbol":"NSE:INFY","product":"CNC","quantity":10,"price":1500,"acquired":"2026-10-26","buy_costs_inr":17.81}`. Positions and lots must reconcile before sales. Use available cash, not unsettled or assumed future proceeds. Provide reconciled daily P&L including unrealized movements. `day_net_cash_flow_inr` is net deposits minus withdrawals since the starting equity snapshot (defaults to zero). Risk also computes marked equity minus start equity minus net flows, and uses the more conservative P&L. The CLI revalues paper P&L on each fill using supplied quotes; it does not continuously mark positions between commands. Direct library fills without prices set P&L to null and require reconciliation before another risk check.

Quote:

```json
{"quotes":{"NSE:INFY":{"price":1500,"currency":"INR","as_of":"2026-10-26T10:00:00+05:30","source":"your verified source","execution_grade":false}}}
```

Never replace a provider timestamp with the retrieval time to make it pass freshness. `execution_grade` is informational: this software only simulates orders, and cannot certify a feed for live trading. `quote` replaces the saved quote map; request every held/proposed symbol to avoid missing valuations. Failed requested symbols are reported and not filled from an old cache.

Instrument master:

```json
{
  "as_of":"2026-10-26", "source":"verified broker/exchange master and current surveillance lists",
  "instruments":{
    "NSE:INFY":{
      "segment":"EQ", "series":"EQ", "active":true,
      "lot_size":1, "tick_size":0.1,
      "lower_band":1350, "upper_band":1650,
      "cas_eligible":true, "surveillance":"NONE",
      "intraday_allowed":true, "broker_symbol":"INFY"
    }
  }
}
```

These numbers are illustrative. Verify each field from current exchange/broker sources; tick sizes are not universally ₹0.05, and a broker can restrict an otherwise listed security. `NONE` means verified no relevant surveillance restriction, not missing information. Unknown metadata blocks planning readiness. An instrument master is a user-verified input, not automatically authenticated by this software.

Order:

```json
{"currency":"INR","paper":true,"status":"proposed","created_at":"2026-10-26T10:00:00+05:30","orders":[{"symbol":"NSE:INFY","side":"BUY","quantity":10,"product":"MIS","order_type":"LIMIT","validity":"DAY","price":1500,"stop_loss":1480}]}
```

Order-level fields beyond this schema are rejected. `stop_loss` is a planning field only. The manual Kite payload omits it; a risk PASS does not place protective orders.

## Research imports

Unless stated otherwise, use JSON `{"rows":[...]}` or CSV with the same column headers. Plain JSON row lists are also accepted. Save UTF-8; BOM is accepted. CSV is supported for normalized tables, not arbitrary downloaded spreadsheets. For XLSX/PDF sources, verify and normalize the relevant rows before import.

Holdings (`copycat`): `symbol,quantity,market_value_inr,as_of,source_url`, or `portfolio_weight_pct` instead of market value. All rows must share the snapshot date and have a single comparable basis. `quantity` is needed for diffs, not for weight-only copying. Never feed issuer ownership percentages as portfolio weights. Example: `examples/holdings.json`.

Quarterly financials (`analyst`): `symbol,period_end,period_type,basis,unit,revenue,net_profit,eps,source_url`. `period_type=quarter`; basis is `consolidated` or `standalone`; unit is `INR`, `lakh` or `crore`. EPS remains INR/share and is not multiplied by the monetary unit. TTM EPS requires four consecutive standard quarter ends. Choose a consistent original/restated series; duplicate quarters are rejected. Example: `examples/results.json`.

Disclosures: `symbol,person,transaction_date,disclosed_at,transaction_type,quantity,source_url`. Transaction date is YYYY-MM-DD; disclosed_at includes IST offset. Retain additional fields such as security type/mode/value when available. Example: `examples/disclosures.json`. Raw `filings insider` output is deliberately not assumed to meet this schema.

News saved-feed input is JSON: `{"rows":[{"id":"stable-id","symbol":"NSE:INFY","title":"...","url":"...","published_at":"2026-10-26T09:30:00+05:30"}],"errors":{}}`. Dedupe is by ID; future and outside-window dated news is excluded. Rows with unknown dates are not claimed to be recent.

Screen input is `{"companies":[...]}` or CSV. Required identity: `symbol`. Metrics are named columns. Rules:

```json
{"rules":[{"metric":"net_margin_pct","op":">=","value":10}],"rank":[{"metric":"revenue_growth_yoy_pct","order":"desc","weight":1}],"top":5}
```

Supported operators: `>`, `>=`, `<`, `<=`, `==`. Missing rule metrics fail. Rank metrics are normalized across passing rows, weighted, with missing rank metrics scored zero and reported. Select one financial basis per company when assembling a screen.

## Tax ledger

Use JSON with `rows`, complete opening buys and chronological fills. Fields: `account,symbol,date,side,quantity,price,delivery,costs_ex_stt_inr`. `delivery` must be a JSON boolean; **tax CSV is not supported without converting this field to a boolean first**. Same-date rows keep input sequence. Account identifies the demat account. Use one canonical security identity for cross-exchange trades in the same ISIN. Supply corporate-action adjusted lots and correct demat FIFO order. Example: `examples/tax-ledger.json`. Read [tax scope](tax.md).

## Calendar overrides and alerts

Copy `data/calendar-2026.json` to workspace `calendar.json` and maintain it against actual exchange circulars. `special_sessions` entries use `{"YYYY-MM-DD":{"open":"HH:MM","close":"HH:MM"}}`; remove a resolved date from `unresolved_sessions` when adding its verified override. Overrides cover the explicitly modeled continuous session only. Do not extend valid_through over a session-rule change without updating the engine and tests.

Alerts are `{"rules":[...]}`. Kinds: `above`, `below`, `stop` (symbol + price), `open` (exchange + cas_eligible), `square_off_reminder` (exchange + cas_eligible + HH:MM time). Each distinct rule fires at most once per IST date. A stopped poller cannot send an alert retroactively at the intended time.
