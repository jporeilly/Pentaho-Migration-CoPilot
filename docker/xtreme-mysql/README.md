# Xtreme in MySQL, rebuilt from the reports themselves

The converted `.prpt` already renders from the rows embedded in its bundle.
That proves the **layout**. It says nothing about the **SQL**, which is the
half a customer actually has to trust — so this stands up a real database
to point it at.

Nothing is downloaded. The schema comes from the `.rpt` files, which declare
every table, column, Crystal value type and length; the data comes from the
rows Crystal saved inside them.

## Run it

```bash
docker compose up -d
```

```bash
.venv/Scripts/pentaho-migrate report-sample-db samples/crystal --only xtreme
```

```bash
docker compose exec -T mysql mysql -uroot -pxtreme < ../../output/sample-db/xtreme.sql
```

Read `output/sample-db/xtreme.manifest.md` before demoing it. What was
rebuilt from the current corpus:

| Table | Columns | With data | Rows |
| --- | ---: | ---: | ---: |
| `CUSTOMER` | 18 | 13 | 106 |
| `Customer` | 18 | 5 | 269 |
| `EMPLOYEE` | 17 | 0 | 0 |
| `FINANCIALS` | 26 | 18 | 4 |
| `ORDERS` | 12 | 9 | 1,996 |
| `ORDERS_DETAILS` | 4 | 1 | 1,659 |
| `PRODUCT` | 9 | 0 | 0 |

## What this is not

**The data is a result set, not a table dump.** Crystal saves what the
report returned — joined, filtered, and only the columns that report
selected. So a column no report selected has no values, and a row every
report's record selection excluded was never saved. Those columns and
tables are still created, so the generated SELECT binds and runs; they
return NULL and nothing respectively until a real datasource is connected.

Say this out loud in a demo. A consultant who presents these tables as the
customer's database will be contradicted by the customer.

`CUSTOMER` and `Customer` are the same logical table in two physical forms
— the Derby build of Xtreme names columns `CUSTOMER_NAME`, the Access build
`Customer Name`. Different reports bind to different ones, so both are kept.
That is also why the container is left at the Linux default
`lower_case_table_names=0`: folding the case would silently lose one.

## Connecting PRD to it

JDBC URL `jdbc:mysql://localhost:3307/xtreme`, user `root`, password
`xtreme`, driver `com.mysql.cj.jdbc.Driver`. The MySQL Connector/J jar goes
in PRD's `lib/jdbc`. In the converted bundle, switch the Data tab from the
inline table to the `source-sql` query — that is the original Crystal SQL,
and it is the whole point of this exercise.
