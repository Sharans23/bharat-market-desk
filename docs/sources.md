# Free sources and evidence

Research checked 26 October 2026. Public access does not grant redistribution rights or guarantee unrestricted automation. Respect source terms; do not circumvent blocks. No paid subscription or API key is required for this project's offline tools. Brokerage accounts and execution-grade market-data services are separate.

| Source | Used for | Access / limitations |
| --- | --- | --- |
| [NSE shareholding patterns](https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern) | Issuer disclosures and attachments | Public website; partial investor visibility, not a complete investor portfolio |
| [NSE insider disclosures](https://www.nseindia.com/companies-listing/corporate-filings-insider-trading) | Public transactions by disclosed persons | Keep security type, mode, transaction dates and publication dates; not all acquisitions are equity market purchases |
| [NSE announcements](https://www.nseindia.com/companies-listing/corporate-filings-announcements) | Company events / original attachments | Website API can return 403; use official downloaded files |
| [NSE financial results](https://www.nseindia.com/companies-listing/corporate-filings-financial-results) | Original results, periods and basis | Automated metadata may be old/incomplete; normalize original results before calculations |
| [BSE corporate filings](https://www.bseindia.com/corporates/ann.html) | Secondary official source and attachments | Manual source for normalized research imports; no BSE execution adapter |
| [AMFI](https://www.amfiindia.com/) and the chosen AMC's portfolio disclosure page | Mutual fund portfolio snapshots | Download the particular scheme and month; fund NAV is not its holdings list; convert XLSX to normalized CSV outside this standard-library importer |
| [NSE market timings](https://www.nseindia.com/resources/exchange-communication-holidays) | Sessions and exchange holidays | Confirm segment and revisions; trading holidays differ from settlement/bank holidays |
| [NSE 2026 cash holiday circular](https://nsearchives.nseindia.com/content/circulars/CMTR71775.pdf) | Bundled 2026 holiday dates | Muhurat timing was separately notified; unresolved sessions are blocked |
| [NSE CAS page](https://www.nseindia.com/static/products-services/closing-auction-session) | CAS eligibility and session boundaries | Current bundled regime separates CAS and non-CAS shares |
| [SEBI October circular index](https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListingAll=yes&sid=1&smid=0&ssid=0) | Further CAS revision notice dated 15 October 2026 | Linked detail page failed retrieval; do not claim its entire implementation was verified. Calendar coverage ends before the reported December transition |
| [Zerodha charges](https://zerodha.com/charges/) | Illustrative NSE cash fee profile | Broker-specific estimate; contract note and current tariff prevail |
| [Zerodha DP explanation](https://support.zerodha.com/category/account-opening/resident-individual/ri-charges/articles/what-do-dp-charges-mean) | Delivery-sale DP estimate | Actual charges depend on account/tariff; one per sell order is a conservative model |
| [Kite order documentation](https://kite.trade/docs/connect/v3/orders/) | Manual payload field names | No live payload submission; authenticated account/data adapters are documented in [broker connections](brokers.md) |
| Yahoo Finance chart endpoint | `.NS` research quotes with provider timestamps | Unofficial; delayed or stale data is possible; no guaranteed execution feed |
| Google News India RSS | Watchlist headlines | Aggregator; verify original publisher/company and distinguish similarly named entities |

The code uses `corporates-pit`, `corporate-announcements`, `corporates-financial-results`, and `corporate-share-holdings-master` as NSE website interfaces. Responses are preserved as raw metadata with source URLs. No official API stability guarantee is claimed.

Observed live behavior is saved in [live-probe.json](live-probe.json). The quote timestamp is preserved as reported, rather than replaced with download time. The successful insider sample included ADR/GDR/FCCB activity and an off-market mode: this is why the software does not automatically convert every raw acquisition into an equity buy signal. The sample financial metadata was historical and cumulative; the quarterly analyst would reject treating it directly as a current quarter.

Additional free reference material: [RBI press releases](https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx), [SEBI](https://www.sebi.gov.in/), company investor-relations releases and annual reports. These are contextual sources, not implemented real-time feeds.
