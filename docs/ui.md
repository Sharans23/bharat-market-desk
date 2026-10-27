# India Trader application — version 1.2

## Open the app

Double-click `launch-app.vbs` in the project folder. This starts the local Python server without a terminal window and opens `http://127.0.0.1:8765` in your browser. Keep the full project folder together. Python 3.10+ must already be installed; no Node installation is needed to run the packaged release because the React production build is included.

If Windows blocks VBScript or the browser does not appear, use `launch-app.cmd` to see diagnostic messages. Developers can run `python -m india_trader.web --open`. Starting the launcher again opens an already-running India Trader server. It does not create a second server on the same port. Use **Stop local app** in the page footer to stop the background process; closing a browser tab alone does not stop it.

## Two separate workspaces

**Practice** is initialized with the original synthetic examples. Its example clock is 26 October 2026 at 10:00 IST and is explicitly shown as enabled. It supports a complete demonstration of allocation, risk, review and paper fill. Turning off the clock causes the old example prices to fail current-time freshness checks.

**Research** starts with zero paper cash, no positions, no targets and no quotes. Import your own reconciled inputs and configure risk limits. These remain paper-planning inputs, not a live broker account. Broker data calls always use actual time, even when Practice is selected.

The workspace selector changes both inputs and results. The application does not overwrite the existing CLI `trader/` folder. To reuse those inputs, import its JSON documents using Data workspace. Data lives in `%LOCALAPPDATA%\IndiaTrader\ui\workspaces\` and uploaded files in `%LOCALAPPDATA%\IndiaTrader\ui\uploads\`, outside the repository/OneDrive.

## Complete service map

| Screen | Services |
| --- | --- |
| Overview | Actual selected-workspace cash, proposed-order count, saved credential presence, quote timestamps and target weights; no invented price charts |
| Portfolio | Broker status, account refresh, saved snapshot report, Kite/Dhan trade books |
| Market data | Broker quotes, public research quotes, quote publication, Kite historical candles and instrument map, CAS-aware session clock |
| Research | News, exchange filings, analyst, screener, copycat/disclosed portfolios, previous-holdings comparison, insider disclosures |
| Trade planner | Budget allocation, stop-based intraday sizing, rebalance, estimated charges |
| Risk checks | Existing risk engine, with individual pass/block explanations |
| Paper orders | Reviewed tickets, explicit checkbox and per-order approval, paper fill, ledger, Kite/Dhan/Groww payload previews |
| Tax & accounting | FIFO realized-gain report and delivery loss candidates |
| Alerts | One requested poll of price/session/exit-reminder rules |
| Connections | Kite browser login, existing-token connection, Dhan/Groww token setup, verification, account refresh, removal |
| Data workspace | File upload, config/targets/alerts forms, JSON imports/edits/exports, schema reference |
| How to use | Guided workflow, service map, limitations, and source/schema/broker/tax references |

Results render as tables and structured fields, with original JSON and download available. Large result tables paginate in groups of 50. Historical charts use returned candle closing prices. Reports and any downloaded exports may contain financial information.

## Connect Kite entirely from the UI

1. Open Connections and follow its developer-console link. Register a Kite developer app if you do not have one.
2. Use `http://127.0.0.1:8765/kite/callback` as the app's redirect URL. This differs from the older CLI's manual-copy localhost example. Keep the UI's displayed origin and port consistent with your developer app.
3. Choose Personal for free account access, or the appropriate data plan if you need quotes and history. See the linked official broker plan documentation for current pricing.
4. Click Connect Zerodha Kite. Enter API key and API secret, then Start Kite login.
5. Click Continue to Zerodha and complete the broker's login/2FA. The registered callback verifies the session and returns to Connections. In the original tab, use “I completed login · refresh” if needed.
6. Click Verify login, then Refresh account. Open Portfolio → Account snapshot to inspect the result.

If your existing app redirects somewhere else, expand the manual redirect option and paste the returned URL or request token into the UI. Do not paste it in chat. Existing access tokens can also be entered directly. Dhan uses client ID + token; Groww uses a token. Broker login, subscription activation and creation of the developer app still happen on the broker's official website.

Credentials are sent over loopback to this local server, then only to the official broker API. Tokens are encrypted with Windows DPAPI; API secrets/request tokens are not persisted. Login attempts expire after ten minutes and pending secrets are removed from memory. Reconnect when the broker session expires. Environment credentials take precedence over saved credentials and are shown in the UI when present. Removal only deletes the saved local credential file.

## Security and boundaries

The server binds only to `127.0.0.1`, checks Host/Origin, uses a per-browser HttpOnly session and CSRF tokens, serves only the built UI, and maps requests to a fixed list of services. File inputs resolve only to bundled examples or uploaded identifiers, not client-supplied filesystem paths. Broker routes remain read/auth-only. Callback queries and secret bodies are not logged. Tokens are never written to browser localStorage/sessionStorage. The server is a single-user local application, not an internet-facing, multi-user brokerage service.

Financial snapshots, workspace files and uploads are ordinary private local files, not encrypted by DPAPI. The application does not merge broker margin balances into deployable paper cash or infer FIFO lots from average holding prices. Live placement/cancellation, derivatives execution, automatic square-off and background alert scheduling remain unimplemented, as in the engine.

## Development and verification

The UI is React + Vite; the backend uses the Python standard library and the existing engine functions. To rebuild UI source, install Node 22.12+ and run `npm ci`, then `npm run build` in `ui/`. The application server serves `ui/dist/` directly on one origin. `npm run dev` is for layout development; authenticated workflow tests should use the built UI served by Python so the origin checks match.

Run Python tests with `python -m unittest discover -s tests -v`. Browser tests use `ui/e2e/app.spec.js` and installed Chrome. Start an isolated server with `python -m india_trader.web --data-dir .ui-test-data`, then run `npx playwright test` in `ui/`. Never point destructive test setup at a real workspace. Synthetic API contract tests cover broker authentication; no real account login is claimed until you complete setup yourself.

Packaging includes source and built assets, and excludes node_modules, test workspaces, browser artifacts, local uploads and credentials. See verification.md for the final observed test results.
