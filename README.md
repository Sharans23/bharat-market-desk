# Bharat Market Desk

A private Indian-equity research and paper-trading workspace with a React UI and Python engine.

**Hosted setup:** [Deploy and sign in](docs/hosting.md). Frontend and backend deploy together from this repository. **Local setup:** use the Windows launcher described below.

# India Trader

## Open the application — version 1.2

Double-click [launch-app.vbs](launch-app.vbs). The React application opens at `http://127.0.0.1:8765`, with every existing service integrated: research, market data, allocation, intraday sizing, risk, reviewed paper orders, tax, alerts and broker accounts. **Connections lets you complete Kite login or enter Dhan/Groww tokens entirely from the UI.** How to use contains the workflow guide and detailed references.

The release includes the built UI: Python 3.10+ is required; Node is needed only for development. Use [launch-app.cmd](launch-app.cmd) if Windows blocks VBScript or to see startup diagnostics. Stop the background service using **Stop local app** in the footer. Read the [application guide](docs/ui.md) for storage, browser login, workspace separation and development.

Practice uses labeled synthetic inputs; Research starts with empty account/quote inputs. No live orders are submitted. Broker credentials and real account login are still supplied by you locally.

Eleven Indian-equity research, portfolio-planning and paper-trading skills, adapted from [Jakeschincariol/trader-skill](https://github.com/Jakeschincariol/trader-skill). Python 3.10+; standard library only; no API key required for the bundled public readers.

This preserves the original research → sizing → risk → reviewed ticket workflow. It adds INR accounting, whole-share orders, Indian session rules, estimated charges and stop-based long intraday sizing. **It is not an autonomous trading bot or a tested profitable strategy.** There is no live order-submission code.

## Broker account/data services

Kite, Dhan and Groww adapters now read authenticated funds, holdings, positions, orders and NSE cash quotes. Kite also supports instrument identifiers and historical candles. Broker subscriptions may be required for data. Account snapshots remain separate from synthetic paper accounts; live orders cannot be submitted.

For your first Kite connection, use **Connections** in the application and register its displayed callback URL. The [older command-line connection guide](docs/brokers.md) and `connect-kite.cmd` also remain available. Credentials are entered locally and saved encrypted for your Windows user, outside the repository. No account has been connected during development.

```powershell
python -m india_trader connections connect kite
python -m india_trader connections sync kite
python -m india_trader connections report kite
```

## Run the included example

Open PowerShell in this directory:

```powershell
python -m india_trader --workspace trader init
python -m india_trader --workspace trader --now '2026-10-26T10:00:00+05:30' budget
python -m india_trader --workspace trader --now '2026-10-26T10:00:00+05:30' risk
python -m india_trader --workspace trader --now '2026-10-26T10:00:00+05:30' broker show
```

All example holdings, instrument settings and prices are **synthetic**, including familiar stock names. `--now` freezes time for the example; omit it for current-time checks. `init` refuses to overwrite existing files. Use another workspace name to start again.

The example allocates a synthetic ₹100,000 account to four whole-share delivery proposals, leaving ₹14,398.47 after modeled buy charges. All four pass the example risk configuration. No approval or fill happens automatically.

For an intraday proposal:

```powershell
python -m india_trader --workspace trader --now '2026-10-26T10:00:00+05:30' intraday NSE:INFY --entry 1500 --stop 1480
python -m india_trader --workspace trader --now '2026-10-26T10:00:00+05:30' broker show
```

This replaces `orders.json` with a proposed long MIS trade. The stop is a planning level, not a placed protective order. No automatic square-off exists.

## The eleven skills

| Skill | Indian adaptation | Command |
| --- | --- | --- |
| [Copycat](skills/india-trader-copycat/SKILL.md) | Fund disclosures / valued equity holdings; quantity diffs | `copycat INPUT` |
| [News](skills/india-trader-news/SKILL.md) | India RSS headlines and NSE announcement metadata | `news NSE:INFY` |
| [Budget](skills/india-trader-budget/SKILL.md) | INR caps, buffer, whole shares and intraday stop sizing | `budget`, `intraday` |
| [Disclosures](skills/india-trader-disclosures/SKILL.md) | Public promoter/insider filings in place of Congress PTRs | `filings insider`, `disclosures INPUT` |
| [Analyst](skills/india-trader-analyst/SKILL.md) | Quarterly results; lakh/crore conversion, YoY and EPS | `analyst INPUT` |
| [Screener](skills/india-trader-screener/SKILL.md) | Rule-based filtering/ranking with missing-data failures | `screen` |
| [Risk](skills/india-trader-risk/SKILL.md) | Quotes, sessions, ticks, circuits, cash, exposure, loss limits | `risk` |
| [Broker](skills/india-trader-broker/SKILL.md) | Kite/Dhan/Groww account reads and payload previews; exact paper approvals and ledger | `connections`, `broker show/approve/fill/log` |
| [Tax](skills/india-trader-tax/SKILL.md) | FIFO, April–March FY, delivery vs non-delivery reporting | `tax report/harvest` |
| [Alerts](skills/india-trader-alerts/SKILL.md) | Price levels, session alerts, exit reminders | `quote`, `clock`, `alerts` |
| [Rebalance](skills/india-trader-rebalance/SKILL.md) | Whole-share drift plans; recheck after each fill | `rebalance --band 5` |

Each skill includes a launcher usable from any working directory:

```powershell
python 'FULL_PATH_TO_REPO/skills/india-trader-risk/scripts/run.py' --workspace 'FULL_PATH_TO_DATA' risk
```

Keep the entire repository together: launchers resolve the shared engine in `india_trader/`. An agent can load a skill's `SKILL.md` directly. The `.claude-plugin/` directory also packages the eleven folders as a local Claude plugin; use the local repository as the plugin directory. Do not copy individual skill folders away from the shared engine.

## Public data and real inputs

```powershell
python -m india_trader quote NSE:INFY NSE:TCS
python -m india_trader news NSE:INFY NSE:TCS
python -m india_trader --out trader/insider-raw.json filings insider NSE:INFY
python -m india_trader --out trader/shareholding-raw.json filings shareholding NSE:INFY
python -m india_trader --out trader/results-raw.json filings results NSE:INFY
python -m india_trader analyst examples/results.json
python -m india_trader screen
python -m india_trader tax report --input examples/tax-ledger.json --fy 2026-27
```

NSE's website APIs are best-effort, undocumented website interfaces. A successful HTTP response does not prove complete or recent coverage. The analyst accepts normalized original financial results; it does not magically turn arbitrary PDFs or old metadata into current financials. CSV/JSON import schemas and exchange links are in [schemas](docs/schemas.md) and [free sources](docs/sources.md).

The [live probe](docs/live-probe.json) records observed connectivity on 26 October 2026: Yahoo quotes and NSE insider/shareholding/financial metadata responded; announcements returned 403. The first financial-results sample was from 2012. These results are evidence of connectivity, not guaranteed provider reliability or current fundamentals.

Before using current data, replace the synthetic account, quotes, target weights and instrument master. Risk requires timestamped INR quotes, today's verified instrument eligibility/ticks/circuit bands and a reconciled IST trading-date account. The default profile covers **NSE main-board cash EQ**, delivery and fully funded long intraday trades. BSE identities work in imported research/tax data; BSE execution planning is deliberately blocked pending a BSE calendar and group-specific fee implementation. Derivatives, SME lots, short entries, leverage, ETFs with different tax treatment and live order APIs are outside this build.

## Verification and maintenance

```powershell
python -m unittest discover -s tests -v
python scripts/live_probe.py
```

The offline suite covers all eleven workflows, batch cash constraints, stale/future quotes, CAS boundaries, costs, FIFO, acknowledgement expiry, changed-input invalidation and replay prevention. The optional live probe only reads public data.

The bundled calendar stops at **6 December 2026**, before the announced further CAS changes; later dates return UNKNOWN. Muhurat and unresolved special sessions also return UNKNOWN until verified overrides are supplied. Refresh calendar, charges and instrument rules from their sources; see [operations](docs/operations.md).

Read [upstream comparison](docs/upstream-comparison.md), [tax scope](docs/tax.md) and [verification](docs/verification.md). MIT license and upstream attribution are retained. This software performs research and arithmetic; it does not promise profitable or accurate future trades.
