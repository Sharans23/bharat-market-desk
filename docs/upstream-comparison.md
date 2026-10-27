# Upstream comparison

Inspected source: https://github.com/Jakeschincariol/trader-skill.git, commit `5189e79b9a480755a3733ac9713f5353981dbe18`. The untouched checkout is in the sibling `upstream-trader/` directory. Upstream contains eleven SKILL.md files, standard-library Python scripts, examples, offline tests and Claude plugin metadata. Its Python helpers do not independently submit orders; agent instructions describe connector handoff.

This adaptation rewrites market-specific implementation around a shared validated schema rather than changing US ticker names in place. Upstream's workflow and feature organization informed the design; its MIT copyright notice is retained in LICENSE. No original author endorsement is implied.

| Original | Replacement / scope decision |
| --- | --- |
| SEC 13F portfolio | Disclosed Indian fund/investor equity sleeve imports; NSE shareholding metadata discovery. No claim of complete 13F-equivalent coverage |
| US 8-K / news feeds | NSE announcements plus India RSS; explicit HTTP errors and normalized offline inputs |
| Dollar/fractional sizing | INR, whole shares, fee reserves, caps and long intraday stop sizing |
| House PTR / Pelosi | Public promoter/insider disclosures. No fabricated politician-trade feed |
| SEC XBRL facts | Exchange result discovery + normalized Indian quarterly results, units and reporting basis |
| Generic screener | Numeric rules and weighted ranking; missing rule metrics fail |
| US asset / margin checks | NSE cash EQ identity, current instrument rules, session/circuit/tick checks and fully funded portfolio limits |
| Alpaca connector ticket | Kite/Dhan/Groww authenticated account/data adapters, broker-specific payload previews, exact paper acknowledgement and local paper-fill ledger. No live order submission |
| US wash sales / tax lots | Indian FIFO, financial-year buckets, delivery/non-delivery distinction and loss candidates |
| NYSE/DST clock | IST, NSE holidays, CAS-aware continuous session and bounded calendar validity |
| Fractional rebalance | Whole-share, capped delivery plans with no assumed unfilled sale proceeds |

Added failure handling: finite-number validation, timezone-aware quote freshness, effective calendar/charges bound into risk context, atomic combined paper account/event updates, process lock, consumed approvals, and explicit synthetic fixtures.

Not implemented: profitable intraday entry signals, backtested performance claims, live brokerage execution, continuously running monitoring, guaranteed free real-time quotes, automatic normalization of every AMC spreadsheet/PDF, derivative contracts/expiry/lot logic, BSE execution, broker margin calculators or tax-return filing. These are concrete boundaries, not hidden dependencies.
