# Broker connections — version 1.1

Version 1.2 adds a complete graphical setup. Open `launch-app.vbs` and select **Connections**. For automatic Kite login return, register `http://127.0.0.1:8765/kite/callback`; see [application setup](ui.md). The manual CLI instructions below remain supported.

Kite is the primary connection. Dhan and Groww implement the same account/data interface. No broker account has been authenticated during development: completing your local login is still required. Tests use synthetic credentials and mocked broker responses, including a real Windows DPAPI round trip with a synthetic token.

## Connect Kite on this Windows computer

1. Register at the [Kite Connect developer console](https://developers.kite.trade/signup). Choose **Personal (free)** to start with account holdings, positions and funds; quotes and historical candles require the paid data plan. Under **My Apps → Create New App**, enter app name `India Trader`, your Zerodha client ID and a short description. Leave the optional postback URL empty. The developer account is separate from normal Kite login. Follow the [official registration instructions](https://support.zerodha.com/category/trading-and-markets/general-kite/kite-api/articles/how-do-i-sign-up-for-kite-connect).
2. For a new local app, register redirect URL `http://127.0.0.1:8000`, which Zerodha documents for testing. Copy the generated API key and API secret into your own secure local storage. This CLI does not run a callback server: after login, the browser may display a connection error at localhost. Copy the full address containing `request_token` from the address bar; the CLI accepts that address or the token itself. For an existing app, keep its registered redirect URL. Do not send either credentials or the redirect URL in chat.
3. Double-click `connect-kite.cmd`, or run from this repository:

```powershell
python -m india_trader connections connect kite
```

4. Enter the key and secret in the hidden local prompts. The command opens the official Kite login page. Complete login and 2FA yourself. Copy the resulting request token or redirect URL into the hidden prompt promptly.
5. The command exchanges the token, checks the authenticated profile, then saves only API key + access token using Windows DPAPI. The API secret and request token are not saved. If verification fails, the previous saved credentials remain untouched.
6. Read your account:

```powershell
python -m india_trader connections status kite
python -m india_trader connections sync kite
python -m india_trader connections report kite
```

The `.cmd` launcher runs the first sync after a successful connection. `report` shows the last saved snapshot and its age; it does not claim that saved data is current. If you already have a valid access token, use `connections connect kite --existing-token`. Add `--no-browser` to print the official login URL instead of opening it.

Kite's documented access token expires at 6 AM the following day and can be invalidated earlier. Run connect again when authentication fails. We do not store passwords, OTPs, TOTP seeds or automate daily broker login. [Official authentication flow](https://kite.trade/docs/connect/v3/user/).

## What is implemented

| Capability | Kite | Dhan | Groww |
| --- | --- | --- | --- |
| Verify authentication | Yes | Yes | Yes |
| Funds, holdings, positions | Yes | Yes | Yes, CASH positions |
| Order book | Yes | Yes | Yes, bounded pagination, CASH |
| Trade book | Yes | Yes | Not implemented |
| NSE cash quotes | Yes | Yes, verified security-ID map required | Yes |
| Instrument identifier/tick download | Yes, NSE EQ CSV | Manual map | Symbol-based |
| Historical candles | Yes, requests limited to 30 days | Not implemented | Not implemented |
| Broker-specific LIMIT payload preview | Yes | Yes | Yes |
| Place/modify/cancel live orders | No | No | No |

This release expands authenticated account visibility and data access. It does not turn the paper risk engine into a live execution system. The HTTP transport permits only the documented account/data routes and Kite token exchange; it rejects order-mutation paths. Broker-issued tokens may still carry broader permissions at the broker itself, so keep them private.

## Market data and paper planning

```powershell
python -m india_trader connections quotes kite NSE:INFY NSE:TCS
python -m india_trader --workspace trader connections quotes kite NSE:INFY NSE:TCS --publish
python -m india_trader --out kite-instrument-map.json connections instruments kite
python -m india_trader --out infy-candles.json connections history kite --instrument-token 408065 --interval 5minute --start '2026-10-26T09:15:00+05:30' --end '2026-10-26T15:15:00+05:30'
```

Verify the instrument token from today's map; the example INFY token is not a substitute for that lookup. Quotes preserve last-trade timestamps, including after-market timestamps. Missing/sentinel timestamps are rejected. `--publish` replaces the paper workspace's quote map only if every requested symbol succeeded. Include all existing holdings and proposed symbols. Risk still checks age and rejects stale data. Never use `--now` with broker commands; connection commands reject simulated time.

An instrument download is a symbol/token/tick map, not a complete eligibility master. Do not replace `instruments.json` with it: it does not verify series, surveillance, CAS eligibility, circuit bands, ETF tax classification or broker intraday permission.

## Dhan and Groww

Generate an official access token through the broker's own developer/account interface, then enter it locally:

```powershell
python -m india_trader connections connect dhan
python -m india_trader connections sync dhan
python -m india_trader connections connect groww
python -m india_trader connections sync groww
```

Dhan additionally asks for client ID and verifies it against the profile. For Dhan quotes/previews, pass `--mapping PATH` containing this shape, with real values from the [official instrument list](https://dhanhq.co/docs/v2/instruments/):

```json
{"instruments":{"NSE:YOUR_SYMBOL":{"dhan":{"security_id":123456789,"exchange_segment":"NSE_EQ"}}}}
```

The ID above is deliberately illustrative, not a tradeable mapping. A security ID is exchange-specific; do not reuse another broker's token. Groww uses the NSE trading symbol directly in this build.

The following environment variables are an alternative to the Windows vault:

| Provider | Variables |
| --- | --- |
| Kite | `KITE_API_KEY`, `KITE_ACCESS_TOKEN` |
| Dhan | `DHAN_CLIENT_ID`, `DHAN_ACCESS_TOKEN` |
| Groww | `GROWW_ACCESS_TOKEN` |

Set secrets through your local secret-management process, not chat or committed files. Environment values take precedence over the vault. A partially configured environment is rejected; it is never merged with saved values from a possibly different account. This also provides an option on non-Windows systems where the built-in DPAPI vault is unavailable.

## Data storage and account meaning

On Windows, encrypted credentials are in `%LOCALAPPDATA%\IndiaTrader\credentials\`. Private broker snapshots are in `%LOCALAPPDATA%\IndiaTrader\snapshots\`. They are outside this OneDrive repository. DPAPI binds credential encryption to the current Windows user. Snapshot financial records are ordinary local JSON under your profile, not encrypted by DPAPI. Nothing is uploaded to a third-party app by this connector.

`sync` saves a snapshot only after all required reads succeed. API reads are sequential, so the snapshot is not an atomic exchange ledger. If a sync fails, the previous file remains with its previous timestamp. Account identity is represented by a stable hash in summaries; snapshots preserve broker financial fields and can contain broker account IDs.

Holdings and positions stay separate to avoid double-counting same-day delivery activity. Pledged, locked and T1 quantities retain their source fields. Broker margin figures are not silently reinterpreted as deployable cash, and average prices are not invented FIFO purchase lots. No command overwrites the paper account with a broker account. Current realized holdings/tax lots and settled funds must be reconciled before building any later execution integration.

`connections forget kite` removes only locally saved credentials. It does not revoke the broker session, clear environment variables or delete snapshots. Revoke a token through the official broker portal if necessary.

## Order review

```powershell
python -m india_trader --workspace trader connections preview kite --index 1
python -m india_trader --workspace trader connections preview dhan --index 1 --mapping dhan-map.json
python -m india_trader --workspace trader connections preview groww --index 1
```

Previews are explicitly `FORMAT_ONLY`, not live risk approvals. They validate the supported cash LIMIT DAY shape and adapt field names/product codes; no network request submits them. The existing `broker approve/fill` commands remain local paper simulation. Stops in proposals are still planning metadata, not placed protective orders. Zerodha example charges must not be used as a verified Dhan/Groww tariff.

## Costs and permissions

The local software has no new third-party Python dependencies. Broker services can charge independently. On the verification date, Kite's Personal plan excludes market data; the Connect data plan is listed at ₹500/month. Dhan distinguishes free trading APIs from paid data access. Groww requires an active API subscription. We have not purchased or enabled any paid plan. Check the official plan pages before subscribing: [Kite plans](https://support.zerodha.com/category/trading-and-markets/general-kite/kite-api/articles/what-are-the-charges-for-kite-apis), [Dhan access](https://dhanhq.co/docs/v2/authentication/), [Dhan data pricing](https://dhan.freshdesk.com/support/solutions/articles/82000909106-how-do-i-get-live-market-data-from-dhan-), [Groww APIs](https://groww.in/trade-api).

Official schema references checked 26 October 2026: [Kite portfolio](https://kite.trade/docs/connect/v3/portfolio/), [Kite quotes/instruments](https://kite.trade/docs/connect/v3/market-quotes/), [Kite historical data](https://kite.trade/docs/connect/v3/historical/), [Dhan portfolio](https://dhanhq.co/docs/v2/portfolio/), [Dhan quote data](https://dhanhq.co/docs/v2/market-quote/), [Groww portfolio](https://groww.in/trade-api/docs/curl/portfolio), [Groww quote data](https://groww.in/trade-api/docs/curl/live-data), [Groww orders](https://groww.in/trade-api/docs/curl/orders).

## Adding another broker

Implement an `Adapter` in `india_trader/brokers/adapters.py`, add its official host and narrowly allowed read/auth routes in `transport.py`, register credential field names and the adapter, and add response-contract tests. Keep token exchange, raw broker-account meaning, quote timestamps, instrument IDs and pagination explicit. Only advertise implemented capabilities. Live submission requires its own reconciliation, broker-specific charges/eligibility, per-order authorization, rejection/timeout handling and order-state model; adding a name to the registry does not supply those features.
