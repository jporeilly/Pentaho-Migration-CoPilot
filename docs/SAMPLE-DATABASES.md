# Sample databases: running the generated SQL for real

A converted `.prpt` renders from the rows embedded in its bundle. That proves
the **layout**. It says nothing about the **SQL**, which is the half a
customer actually has to trust — "here is the query we generated from your
report" invites the obvious question, *does it run?*

This is how to answer that question with a live database, built from the
reports themselves. Nothing is downloaded, and no customer database is needed.

## Where the database comes from

Both halves are already in the `.rpt` files.

**Schema** comes from the dumps. Every report declares its tables, columns,
Crystal value types and lengths — including columns no report reads. That is
a real schema, so the generated SELECT binds against it.

**Data** comes from the rows Crystal saved inside the reports. Splitting a
saved result set back into base tables works because Crystal keeps the
qualified name: a saved column `CUSTOMER_NAME` is declared as
`CUSTOMER.CUSTOMER_NAME`. A short name owned by two tables is a join key and
is written to both, so the joins resolve. One customer with thirty invoices
dedupes to one `CUSTOMER` row and thirty `ORDERS` rows.

```bash
.venv/Scripts/pentaho-migrate report-sample-db samples/crystal --only xtreme
```

`--only` filters to reports whose connection metadata mentions the string, so
the same command builds any corpus subset — or a customer's own folder, which
is the case this exists for: during a PoC there is usually no database to
point at, because the DBA is away or the schema is confidential.

## What is loaded here

| Schema | Contents | Rows | Built by us |
| --- | --- | ---: | --- |
| `sampledata` | Pentaho's Steel Wheels — pre-existing | 19 tables | no |
| `xtreme` | Crystal's own Xtreme sample DB | 4,034 | yes |
| `boe_samples` | SAP BOE XI 4.0 shipped samples | 9,780 | yes |

Steel Wheels is unrelated to the Crystal corpus and **no report binds to it**
— it has `CUSTOMERS`/`ORDERFACT`, the reports want `CUSTOMER`/`ORDERS`. Ten
corpus reports do reference `CUSTOMERS`/`EMPLOYEES`/`PRODUCTS`, but their
columns are `CustomerID`/`CompanyName`: those are **Northwind**, and the name
overlap is coincidence. (Northwind is not worth standing up — none of its
seven reports carries saved data, so none can render in the Crystal viewer,
so there is no original to show beside the conversion.)

## Connecting

Server `localhost:3306` (container `mysql-database-1`, MySQL 9.5), Adminer at
<http://localhost:8050>.

| User | Access |
| --- | --- |
| `root` / `password` | everything |
| `pentaho` / `password` | `ALL` on `sampledata`, `SELECT` on `xtreme` and `boe_samples` |

Connector/J (`mysql-connector-j-8.4.0.jar`, from Maven Central) is installed
in `design-tools/report-designer/lib/jdbc/`. PRD will not offer MySQL as a
connection type until it is there, and needs a restart after it appears.

Three **JNDI names** are registered in `~/.pentaho/simple-jndi/default.properties`,
so a converted bundle resolves a name rather than carrying a URL:

| JNDI name | Schema |
| --- | --- |
| `Xtreme` | `xtreme` |
| `BOE_Samples` | `boe_samples` |
| `SteelWheelsMySQL` | `sampledata` |

Pentaho's own `SampleData` entry is untouched and still points at HSQLDB.

Convert straight onto one:

```bash
.venv/Scripts/pentaho-migrate report samples/crystal/demo/Statement_of_Account.xml --jndi Xtreme
```

Then in Report Designer switch the Data tab from the inline table to the
**`source-sql`** query. That is the original Crystal SQL, and running it is
the whole point.

### Only Xtreme is wired end to end

`--jndi Xtreme` works: the demo statement's generated SELECT runs against the
`xtreme` schema and returns its rows joined correctly.

**`--jndi BOE_Samples` resolves but its reports' SQL will not run.** A BOE
report emits `FROM "dataroot/Customer_Query", "dataroot/Orders_Query"` while
the rebuilt schema has `Customer` and `Orders` — `generate_sql` names tables
from `Table/@Name`, the rebuild from the qualified-name prefix, and the two
agree for Xtreme but not for XML datasources. The `/` also forces ANSI double
quotes, which MySQL rejects without `ANSI_QUOTES`, and the query carries no
join condition. Until that is reconciled, treat `boe_samples` as **data
only** and do not demo a Data-tab switch on a BOE report.

## Rebuilding and reloading

```bash
.venv/Scripts/pentaho-migrate report-sample-db samples/crystal --only xtreme
```

```bash
docker cp output/sample-db/xtreme.sql mysql-database-1:/tmp/xtreme.sql
```

```bash
docker exec mysql-database-1 sh -c "mysql -uroot -ppassword --default-character-set=utf8mb4 < /tmp/xtreme.sql"
```

**Copy the file in; do not pipe it.** `Get-Content x.sql | docker exec -i …`
re-encodes through the console codepage and double-encodes every non-ASCII
character on the way — `ô` arrives as `C3 83 C2 B4`. It loads *without error*,
which is what makes it dangerous. `docker cp` moves bytes. Pass
`--default-character-set=utf8mb4` for the same reason.

The script is idempotent: it creates the database if absent and drops and
recreates only its own tables. It never touches `sampledata`.

## What this is not — say it out loud in a demo

Read the generated `output/sample-db/<name>.manifest.md`. A consultant who
presents these tables as the customer's database will be contradicted by the
customer.

**The data is a result set, not a table dump.** Crystal saves what the report
returned — joined, filtered, and only the columns that report selected. A
column no report selected has no values; a row every record selection excluded
was never saved. Those columns and tables are still created so the SELECT
binds and runs, but they return NULL and nothing.

That is why `xtreme.ORDERS` holds 1,996 rows while only 345 join to a customer
with a name: the report contributing most of those orders only ever selected
`COUNTRY`. Coverage per table is in the manifest.

**Join keys may be synthesized.** A report printing a customer's name and its
order amounts does not select `CUSTOMER_ID`, so Crystal never saved it — and
without a key the generated SELECT joins to nothing and returns zero rows,
which reads as a broken conversion when it is thin data. Each saved row *is*
one line of a joined result set, so an order is only ever keyed to the
customer it actually arrived with: **the relationship is real, the number is
not.** Where a report did select the key, the customer's own value always
wins. Synthesized columns are listed in the manifest. Never present those
numbers as the customer's identifiers, and never carry them downstream.

## Known wrinkles

- `xtreme` carries both `CUSTOMER` and `Customer` — the same logical table in
  two physical forms (the Derby build of Xtreme names columns `CUSTOMER_NAME`,
  the Access build `Customer Name`). Different reports bind to different ones,
  so both are kept. The server must stay at `lower_case_table_names=0` or one
  is silently lost.
- `boe_samples` carries `variance_xtab` twice, the second as
  `dataroot_variance_x005F_xtab` — `_x005F_` is the XML name-escape for an
  underscore, decoded for chart columns but not yet for table names. Same
  2,393 rows; ignore the duplicate.
- Three `Region` values in `xtreme.Customer` read `Provence-Alpes-Côte
  d<19><2041>zur`. rpt-rs returns two codepoints misaligned for that value, so
  it is upstream of the byte-order repair rather than a defect in it.
