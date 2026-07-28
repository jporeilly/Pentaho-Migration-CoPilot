# Consultant Report: Statement_of_Account

## Release check — rendered original vs rendered conversion

**⚠ REVIEW** — differences found; each one is listed below with a proposed resolution or consultant guidance.

- Original render: **74 pages** (SAP Crystal viewer, saved data)
- Converted render: **37 pages** (Pentaho Reporting engine, embedded data)
- Statement pagination: **36 of 36** group(s) take the same NUMBER of pages as the original

### Findings

**1. ℹ [pages] the conversion is more compact: 37 pages vs 74 - the original leaves near-empty spill pages (43 of them) that the conversion consolidates; every statement still spans the same pages as the original**
   - *No automatic resolution - consultant judgment needed.*

**2. ⚠ [appearance] REPORT-WIDE: the middle of the page differs on 37 of the 37 page(s) compared. It is one difference in a band that repeats, not one per page - a single fix covers every statement**
   - `18%-23% of each page affected`
   - `e.g. original p47 vs converted p24 (23% of the page)`
   - *No automatic resolution - consultant judgment needed.*

## Action plan

**4 action(s), 0.61h ($92) in total.** Highest priority first; within a priority, the heaviest first.

- P2 · correctness: **0.51h** ($76) across 4 item(s)
- P3 · cosmetic: **0.10h** ($15) across 1 item(s)

| # | Priority | Action | Items | Effort |
|---|---|---|---|---|
| 1 | P2 · correctness | Review the flagged layout differences | 1 | 0.25h ($38) |
| 2 | P2 · correctness | Wire up the data source | 1 | 0.20h ($30) |
| 3 | P2 · correctness | Glance over the formulas that translated with a caveat | 2 | 0.06h ($9) |
| 4 | P3 · cosmetic | Work through the remaining notes | 1 | 0.10h ($15) |

### 1. Review the flagged layout differences

*P2 · correctness · 1 item(s) · 0.25h ($38)*

**Why it matters.** Content that reflowed or pages that filled differently. Not wrong data, but the customer notices a total that slipped onto its own page.

**How.** In Report Designer, check band heights and the Keep Together flag on the groups named below (right-click the group band > Attributes).

Where: `appearance`

- REPORT-WIDE: the middle of the page differs on 37 of the 37 page(s) compared. It is one difference in a band that repeats, not one per page - a single fix covers every statement

### 2. Wire up the data source

*P2 · correctness · 1 item(s) · 0.20h ($30)*

**Why it matters.** The bundle carries 53 rows recovered from the .rpt so it opens and renders with no database. That is a preview dataset, not a live feed.

**How.** When the customer is ready for live data, Data tab > swap the inline table for the JNDI datasource already defined in the bundle (SampleData), then verify the generated SELECT - joins and aliases especially.

Where: `SampleData`


### 3. Glance over the formulas that translated with a caveat

*P2 · correctness · 2 item(s) · 0.06h ($9)*

**Why it matters.** These produce a value; the question is whether it is the value Crystal produced. Scope and rounding are the usual differences.

**How.** Compare each against the Crystal original - the conversion report prints them side by side.

Where: `Late Invoices`, `statement amount`

- Late Invoices: Crystal If without Else: default branch emitted (0) to match Crystal's implicit default
- statement amount: Sum aggregate rewritten as a PRD TotalGroupSumFunction over [ORDER_AMOUNT] grouped by [CUSTOMER_NAME] - verify scope matches the Crystal placement

### 4. Work through the remaining notes

*P3 · cosmetic · 1 item(s) · 0.10h ($15)*

**Why it matters.** Items that need a judgement call but do not fall into a group.

**How.** Each note names what the pipeline found and why it stopped.

- special field in text rendered as "page n / m" ($(PageofPages)) - adjust the format in PRD if the report showed only the bare number

---

# Conversion Report: Statement_of_Account

- **Source:** `samples\crystal\demo\Statement_of_Account.xml`
- **Output:** `samples\crystal\demo\Statement_of_Account.prpt`
- **Sections:** 21 | **Elements:** 41 | **Groups:** 2 | **Parameters:** 0 | **Summaries:** 3
- **Formulas:** 3 auto, 2 need review, 0 manual

## Data source

- JNDI connection: `SampleData` — create/verify this connection on the Pentaho Server (or swap to a native JDBC datasource in PRD).
- The report used linked tables, not a SQL command. A SELECT was generated from the columns the layout references — **verify joins and aliases**:

```sql
SELECT
  CUSTOMER.COUNTRY,
  CUSTOMER.CUSTOMER_NAME,
  CUSTOMER.ADDRESS1,
  CUSTOMER.ADDRESS2,
  CUSTOMER.POSTAL_CODE,
  ORDERS.ORDER_DATE,
  ORDERS.ORDER_ID,
  ORDERS.PO_NUM,
  ORDERS.ORDER_AMOUNT
FROM ORDERS
JOIN CUSTOMER ON ORDERS.CUSTOMER_ID = CUSTOMER.CUSTOMER_ID
ORDER BY CUSTOMER.COUNTRY, CUSTOMER.CUSTOMER_NAME
```

### Record selection formula (MANUAL)

Crystal's record selection must be folded into the SQL WHERE clause or a PRD filter expression:

```
(   (  {ORDERS.PAYMENT_RECEIVED} = "False"  AND  {ORDERS.SHIPPED} = "True"  )   AND  {ORDERS.ORDER_AMOUNT} > 0  )
```

## Formulas

| Formula | Status | Result / Notes |
|---|---|---|
| {@due date} | OK | `=DATE(YEAR([ORDER_DATE]);MONTH([ORDER_DATE]);DAY([ORDER_DATE]) + 30)` |
| {@Late Invoices} | REVIEW | `=IF([due date] < TODAY();[ORDER_AMOUNT];0)` — Crystal If without Else: default branch emitted (0) to match Crystal's implicit default |
| {@statement amount} | REVIEW | `statement amount = TotalGroupSumFunction(field: ORDER_AMOUNT, group: CUSTOMER_NAME)` — report function generated in the bundle (Data tab > Functions in PRD) — Sum aggregate rewritten as a PRD TotalGroupSumFunction over [ORDER_AMOUNT] grouped by [CUSTOMER_NAME] - verify scope matches the Crystal placement |
| {@Xtreme Address} | OK | `="2001 Meridian Way, Vancouver, BC, Canada  V6G 3G6"` |
| {@Xtreme phone/fax} | OK | `="Phone: (604) 681-3435     Fax: (604) 681-2934"` |

## Summaries -> report functions

| Crystal summary | PRD function | Field | Group |
|---|---|---|---|
| Sum ({ORDERS.ORDER_AMOUNT}, {CUSTOMER.CUSTOMER_NAME}) | `Sum_ORDER_AMOUNT_CUSTOMER_NAME` (Sum) | {ORDERS.ORDER_AMOUNT} | CUSTOMER_NAME |
| Sum ({@Late Invoices}, {CUSTOMER.COUNTRY}) | `Sum_Late_Invoices_COUNTRY` (Sum) | {@Late Invoices} | COUNTRY |
| Sum ({@Late Invoices}, {CUSTOMER.CUSTOMER_NAME}) | `Sum_Late_Invoices_CUSTOMER_NAME` (Sum) | {@Late Invoices} | CUSTOMER_NAME |

## Remaining manual work

- `PageFooter`: special field in text rendered as "page n / m" ($(PageofPages)) - adjust the format in PRD if the report showed only the bare number

<details><summary>Fixed automatically during conversion (11) — verify, no action expected</summary>

- conditional EnableSuppress converted to a 'visible' style expression (section GroupHeader2Section6) - verify against Crystal: {Sum_Late_Invoices_CUSTOMER_NAME} <>0
- conditional EnableSuppress converted to a 'visible' style expression (section GroupHeader2Section11) - verify against Crystal: {Sum_Late_Invoices_CUSTOMER_NAME} <>1
- conditional EnableSuppress converted to a 'visible' style expression (section GroupHeader2Section5) - verify against Crystal: {Sum_Late_Invoices_CUSTOMER_NAME} < 2
- layout auto-fit: GroupHeader G2 - 2 text box(es) grown to fit their font (descenders would have clipped); verify nothing now touches the element below
- layout auto-fit: GroupHeader G2 - 1 text box(es) grown to fit their font (descenders would have clipped); verify nothing now touches the element below
- layout auto-fit: GroupHeader G2 - 1 text box(es) grown to fit their font (descenders would have clipped); verify nothing now touches the element below
- layout auto-fit: GroupHeader G2 - 1 text box(es) grown to fit their font (descenders would have clipped); verify nothing now touches the element below
- layout auto-fit: GroupHeader G2 - 1 text box(es) grown to fit their font (descenders would have clipped); verify nothing now touches the element below
- layout auto-fit: GroupHeader G2 - 5 text box(es) grown to fit their font (descenders would have clipped); verify nothing now touches the element below
- layout auto-fit: Detail - 5 text box(es) grown to fit their font (descenders would have clipped); verify nothing now touches the element below
- layout auto-fit: GroupFooter G2 - 1 text box(es) grown to fit their font (descenders would have clipped); verify nothing now touches the element below

</details>

<details><summary>How things were recovered (3)</summary>

- `PageHeader`: image carved from the .rpt binary and matched by aspect ratio - verify it is the right picture
- `GroupHeader`: image carved from the .rpt binary and matched by aspect ratio - verify it is the right picture
- `PageFooter`: image carved from the .rpt binary and matched by aspect ratio - verify it is the right picture

</details>

---
*Generated by Pentaho Migration Copilot. Open the .prpt in Pentaho Report Designer, fix the flagged items, then publish to the Pentaho Server.*