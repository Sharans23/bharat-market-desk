# Tax scope

`tax report` performs FIFO ledger arithmetic and financial-year classification, assuming delivery equity holdings are capital assets. It does not calculate a final tax bill. Income character can depend on facts; broker CNC/MIS labels alone do not decide delivery settlement or tax treatment.

Under the referenced guidance, listed qualifying equity capital gains use a more-than-12-month long-term holding period. For qualifying transfers on/after 23 July 2024, the published special-rate framework includes 20% short-term and 12.5% long-term rates, with the ₹1.25 lakh annual threshold for covered long-term gains. Surcharge, cess, exemptions and eligibility conditions are additional; the code does not apply a misleading flat percentage to every gain. [Income Tax Department: income treatment](https://www.incometaxindia.gov.in/w/treatment-of-income-from-different-sources-1).

Non-delivery cash-equity round trips are separately reported as `SPECULATIVE_BUSINESS`; do not apply the delivery special rates to them. Eligible derivatives have different treatment and are not handled by this cash-equity ledger. [Income Tax Department: speculative transactions](https://www.incometaxindia.gov.in/w/section-43-54).

FIFO is maintained separately per demat account and security; use a consistent identity across NSE/BSE executions of the same ISIN. The simple schema uses `symbol` as that canonical identity: normalize cross-exchange trades of the same holding before import. Transfers, mixed physical/demat histories and corporate actions need adjusted opening lots, including correct demat entry order. [CBDT Circular 768](https://wmstatic-prd.incometaxindia.gov.in/web/guest/w/768-circular-no.-768-dated-24-6-1998-1).

Supply `costs_ex_stt_inr` for eligible acquisition/transfer costs. Capital-gain STT exclusion differs from business-expense treatment; the report does not derive tax deductibility from the trading fee estimate. The business bucket is therefore a pre-additional-adjustments result, not a complete taxable business-income computation.

Further exclusions: pre-2018 grandfathering, bonus/split/merger cost adjustments, dividends, buybacks, off-market transfers, business vs investment characterization, basic exemption interactions, loss set-off/carry-forward, audit applicability and tax-regime choices. Preserve the broker tax P&L and contract notes for reconciliation. There is no imported US 30-day wash-sale filter or HIFO selection. A loss candidate is not automatically the FIFO lot that would be sold.
