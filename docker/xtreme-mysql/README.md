# Xtreme in MySQL, rebuilt from the reports themselves

The converted `.prpt` already renders from the rows embedded in its bundle.
That proves the **layout**. It says nothing about the **SQL**, which is the
half a customer actually has to trust — so this stands up a real database
to point it at.

Nothing is downloaded. The schema comes from the `.rpt` files, which declare
every table, column, Crystal value type and length; the data comes from the
rows Crystal saved inside them.

## Run it

`xtreme` is a **separate schema**, so it sits happily alongside Pentaho's
own `sampledata` (Steel Wheels) in the same server. Note that the two are
unrelated: Steel Wheels has `CUSTOMERS`/`ORDERFACT`, Xtreme has
`CUSTOMER`/`ORDERS`, and the Crystal reports bind only to the latter.

Against an existing MySQL container (e.g. `mysql-database-1`):

```bash
.venv/Scripts/pentaho-migrate report-sample-db samples/crystal --only xtreme
```

```bash
docker cp output/sample-db/xtreme.sql mysql-database-1:/tmp/xtreme.sql
```

```bash
docker exec mysql-database-1 sh -c "mysql -uroot -p\"\$MYSQL_ROOT_PASSWORD\" --default-character-set=utf8mb4 < /tmp/xtreme.sql"
```

Or `docker compose up -d` here for a dedicated server on port 3307.

**Copy the file in; do not pipe it.** `Get-Content x.sql | docker exec -i …`
re-encodes the text through the console codepage and double-encodes every
non-ASCII character on the way — `ô` arrives as `C3 83 C2 B4`. It loads
without error, which is what makes it dangerous. `docker cp` moves bytes.
Pass `--default-character-set=utf8mb4` for the same reason.

What was rebuilt from the current corpus:

| Table | Columns | With data | Rows |
| --- | ---: | ---: | ---: |
| `CUSTOMER` | 18 | 13 | 106 |
| `Customer` | 18 | 5 | 269 |
| `EMPLOYEE` | 17 | 0 | 0 |
| `FINANCIALS` | 26 | 18 | 4 |
| `ORDERS` | 12 | 9 | 1,996 |
| `ORDERS_DETAILS` | 4 | 1 | 1,659 |
| `PRODUCT` | 9 | 0 | 0 |

The demo statement's own generated SELECT runs against this and returns its
rows joined correctly — customer, address, order, amount.

## What this is not

Read `output/sample-db/xtreme.manifest.md` before demoing it.

**The data is a result set, not a table dump.** Crystal saves what the
report returned — joined, filtered, and only the columns that report
selected. So a column no report selected has no values, and a row every
report's record selection excluded was never saved. Those columns and
tables are still created, so the generated SELECT binds and runs; they
return NULL and nothing respectively until a real datasource is connected.

That is why `ORDERS` holds 1,996 rows but only 345 of them join to a
customer with a name: the report contributing most orders only ever
selected `COUNTRY`, so its customers have nothing else to show.

**`CUSTOMER_ID` is synthesized.** No report selected it, so Crystal never
saved it — and without a key the generated SELECT joins to nothing and
returns zero rows, which reads as a broken conversion when it is thin data.
Each saved row *is* one line of a joined result set, so an order is only
ever keyed to the customer it actually arrived with: the relationship is
real, the number is not. Never present those values as the customer's IDs.

Say all of this out loud in a demo. A consultant who presents these tables
as the customer's database will be contradicted by the customer.

`CUSTOMER` and `Customer` are the same logical table in two physical forms
— the Derby build of Xtreme names columns `CUSTOMER_NAME`, the Access build
`Customer Name`. Different reports bind to different ones, so both are kept,
and the server must be left at `lower_case_table_names=0` or one is lost.

## Connecting PRD to it

JDBC URL `jdbc:mysql://localhost:3306/xtreme` (3307 for the compose file
here), driver `com.mysql.cj.jdbc.Driver`. The MySQL Connector/J jar goes in
PRD's `lib/jdbc`. In the converted bundle, switch the Data tab from the
inline table to the `source-sql` query — that is the original Crystal SQL,
and running it is the whole point of this exercise.
