# CSCU Talend demo set (talend_demo)

Four authored `.item` jobs backed by the live `cscu_core` credit-union
schema — the ETL walkthrough twin of the Crystal `cr_demo` ladder. Authored
in the same XML shapes real Talend Open Studio emits; regenerate with
`python samples/talend_demo/build_jobs.py`.

| Job | Demonstrates | Converts to |
|---|---|---|
| `members_export` | tPostgresqlInput query → tSortRow criteria → tFileOutputDelimited | .ktr — Table input + Sort rows + Text file output, fully configured (96/100 A) |
| `branch_balances` | join query → tAggregateRow GROUPBYS/OPERATIONS | .ktr — Group By with sum/count aggregates (91/100 A) — the **Try Talend** sample |
| `high_value_txns` | tFilterRow simple conditions (`TXN_AMT >= 10000`) | .ktr — Filter rows condition tree (92/100 A) |
| `cscu_nightly` | tPrejob + three tRunJob calls chained OnSubjobOk | **.kjb** with TRANS entries wired to the three .ktr files above |

Walkthrough: drop any job on the Upload page (or click **Try Talend**),
then Parse → Map → Generate → Validate. Batch them into the Project page
with `pentaho-migrate batch samples/talend_demo`. Before running the .ktr
files in Spoon, create a PostgreSQL connection to the CSCU sandbox
(192.168.1.200:5433 / cscu_core) — generated transformations carry empty
connection placeholders by design.
