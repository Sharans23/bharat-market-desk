# Hosted release verification (1.3)

- Production React build passed.
- All 8 Chrome browser workflows passed against disposable local/hosted workspaces.
- All 138 Python tests passed, including 11 hosted authentication/storage tests.
- Render Blueprint validated against its current public JSON Schema.
- Private runtime files and credential artifacts excluded from Git and Docker builds.
- Actual broker account authentication requires the owner's credentials and was not exercised.
- Deployment status is separate from these local checks; consult the live Render service.

# Verification record

## Version 1.2 graphical application — 27 October 2026

- **127 Python tests passed**: original engine and broker tests plus 15 application/HTTP tests. These cover workspace isolation, atomic initialization after disk failure, complete paper approval/fill/replay behavior, example research and tax workflows, file-path restrictions, input-change invalidation, callback state/expiry, failed login preserving credentials, CSRF/Origin/Host checks and secret-safe errors.
- **7 Chrome end-to-end tests passed** against the built React UI: every service screen, allocation/risk/approval/fill, analyst/screener/holdings comparison/tax/alerts, upload and persisted settings, workspace separation, broker-login initiation/cancellation, phone layouts without horizontal document overflow, and stopping the local server from the UI. The six workflow checks passed together; the final shutdown check passed separately against that same build.
- The production Vite build succeeded. All eleven regenerated skill entrypoints validated. Desktop overview/connections and mobile login screenshots were visually reviewed.
- Broker authentication exchange/callback tests use synthetic credentials and mocked responses. Browser tests start/cancel a synthetic Kite flow and do not visit the external login page. A real broker login and subscription-dependent data access still require the user's setup; no real account has been connected or live order submitted.
- A disk-full error interrupted an early test run. Generated dependency source maps were removed; after disk space became available, all tests were rerun successfully. A failed initialization can no longer leave a partially created workspace.

The packaged application includes compiled React assets; Node/npm are not required for normal use. Python remains required. All operations continue to use the same validated Python engine.

## Earlier command-line releases

Environment: Windows PowerShell, Python 3.11.2. Runtime uses only Python's standard library. Source review and first full verification: 26 October 2026.

The offline suite is run with `python -m unittest discover -s tests -v`. Version 1.1 result: **112 tests passed** (76 original workflow tests plus 36 broker/storage/packaging tests). It includes complete CLI research → plan → risk → exact approval → paper fill → replay rejection, plus all eleven feature workflows. Tests use synthetic fixtures and isolated temporary accounts; no broker order is submitted. All eleven skill folders passed the bundled skill-creator `quick_validate.py`; its PyYAML dependency was installed only in the excluded `.validation-deps/` development folder. Python compilation also passed.

Meaningful checks cover:

- Whole-share allocation, caps and available cash after estimated charges.
- Stop-based sizing and missing/invalid stops.
- Nonfinite numbers, booleans as quantities and malformed configuration.
- Quote currency, stale/future timestamps and missing holding valuations.
- Holiday/weekend/CAS boundaries, IST conversion and unknown coverage.
- Current instrument metadata, surveillance, circuit bands, tick sizes and identity.
- Batch duplicates, aggregate spending, existing holdings, daily-loss halt and exits.
- No sale against a proposed purchase; no cash credit for an unfilled sale.
- Exact-order acknowledgements, expiry, changed inputs, limit bounds and replay prevention.
- Disclosed equity weights, ownership-percent rejection, reporting basis and missing-quarter TTM.
- Missing-data screening, ranking, feed filtering and deduplication.
- April–March tax years, holding-period boundaries, separate account FIFO and non-delivery P&L.
- Unrealized losses trigger the daily halt even when imported P&L is optimistic; paper round-trip P&L reconciles to the change in cash after fees.
- All skill launchers use the same engine and work outside the repository working directory.

See [live-probe.json](live-probe.json) for actual network observations. No assertion of complete exchange coverage is inferred from these probes. Offline correctness tests are separate from network availability checks. Runtime risk checks intentionally reject example quote timestamps when run at a different current time.

This is a tested local toolkit, not an audited brokerage service, calibrated execution simulator or validated investment strategy. Future exchange, broker, tax and website-interface changes require review.

Version 1.1 adds mocked official-response contract checks for Kite, Dhan and Groww; authentication checksums and headers; rejected credentials; failed login preserving saved credentials; Windows DPAPI encryption/decryption with a synthetic token; partial snapshots/quotes; pagination; last-trade timestamps; forbidden order endpoints; redirects; secret-safe errors; and release exclusion of private accounts/tokens. The complete suite passed under the actual Windows user because DPAPI needs the user profile (the sandbox profile could not perform that check). No real broker credentials were supplied, no account login was performed, and live broker response contracts remain to be confirmed during user setup.
