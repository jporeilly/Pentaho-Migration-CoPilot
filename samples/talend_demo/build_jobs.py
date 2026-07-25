"""Generate the CSCU Talend demo set: four .item jobs of increasing scope,
backed by the live cscu_core schema so each converts to a runnable-shaped
.ktr (and the orchestrator to a .kjb) — the ETL walkthrough twin of the
Crystal cr_demo ladder. Authored in the SAME XML shapes real Talend Open
Studio emits (talendfile:ProcessType, elementParameter/TABLE rows, typed
metadata columns, FLOW + SUBJOB_OK connections).

Run:  python samples/talend_demo/build_jobs.py
"""

import json
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

OUT = Path(__file__).parent

HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<talendfile:ProcessType xmi:version="2.0" xmlns:xmi="http://www.omg.org/XMI" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
    'xmlns:talendfile="platform:/resource/org.talend.model/model/TalendFile.xsd" '
    'defaultContext="Default" jobType="Standard">\n'
    '  <context confirmationNeeded="false" name="Default"/>\n')


def param(name, value, field="TEXT"):
    return f'    <elementParameter field="{field}" name="{name}" value={quoteattr(value)}/>\n'


def table_param(name, rows):
    out = [f'    <elementParameter field="TABLE" name="{name}">\n']
    for row in rows:
        for ref, value in row.items():
            out.append(f'      <elementValue elementRef="{ref}" value={quoteattr(value)}/>\n')
    out.append("    </elementParameter>\n")
    return "".join(out)


def metadata(name, columns):
    cols = "".join(
        f'      <column name="{c}" type="{t}" nullable="true" length="0" precision="0"/>\n'
        for c, t in columns)
    return (f'    <metadata connector="FLOW" name="{name}">\n{cols}    </metadata>\n')


def node(component, unique, x, y, extra="", columns=None):
    meta = metadata(unique, columns) if columns else ""
    return (f'  <node componentName="{component}" componentVersion="0.1" '
            f'offsetLabelX="0" offsetLabelY="0" posX="{x}" posY="{y}">\n'
            f'{param("UNIQUE_NAME", unique)}{extra}{meta}  </node>\n')


def flow(source, target, label="row1"):
    return (f'  <connection connectorName="FLOW" label="{label}" lineStyle="0" '
            f'metaname="{source}" source="{source}" target="{target}"/>\n')


def subjob_ok(source, target):
    return (f'  <connection connectorName="SUBJOB_OK" label="OnSubjobOk" lineStyle="1" '
            f'metaname="{source}" source="{source}" target="{target}"/>\n')


def java(value):
    """A Talend Java string literal as it appears in .item attributes."""
    return '"' + value.replace('"', '\\"') + '"'


def pg_input(unique, sql, columns, x=100):
    extra = (param("QUERY", java(sql), field="MEMO_SQL")
             + param("HOST", java("192.168.1.200")) + param("PORT", java("5433"))
             + param("DBNAME", java("cscu_core")) + param("SCHEMA_DB", java("cscu_core")))
    return node("tPostgresqlInput", unique, x, 100, extra, columns)


def file_out(unique, filename, columns, x=700):
    extra = (param("FILENAME", java(filename))
             + param("FIELDSEPARATOR", java(";"))
             + param("INCLUDEHEADER", "true", field="CHECK"))
    return node("tFileOutputDelimited", unique, x, 100, extra, columns)


def build(filename, body):
    (OUT / filename).write_text(HEADER + body + "</talendfile:ProcessType>\n",
                                encoding="utf-8")
    print("wrote", filename)


MEMBER_COLS = [("MBR_NO", "id_String"), ("FIRST_NM", "id_String"),
               ("LAST_NM", "id_String"), ("CITY", "id_String"),
               ("MBR_STATUS", "id_String")]

BAL_COLS = [("BR_NAME", "id_String"), ("BAL_AMT", "id_BigDecimal")]
AGG_COLS = [("BR_NAME", "id_String"), ("TOTAL_BAL", "id_BigDecimal"),
            ("ACCOUNTS", "id_Integer")]

TXN_COLS = [("TXN_DT", "id_Date"), ("ACCT_NO", "id_String"),
            ("TXN_TYPE_CD", "id_String"), ("TXN_AMT", "id_BigDecimal")]


def members_export():
    body = (
        pg_input("tPostgresqlInput_1",
                 'SELECT mbr_no AS "MBR_NO", first_nm AS "FIRST_NM", last_nm AS "LAST_NM",\n'
                 '       city AS "CITY", mbr_status AS "MBR_STATUS"\nFROM cscu_core.members',
                 MEMBER_COLS)
        + node("tSortRow", "tSortRow_1", 400, 100,
               table_param("CRITERIA", [
                   {"COLNAME": "LAST_NM", "SORT": "alpha", "ORDER": "asc"},
                   {"COLNAME": "FIRST_NM", "SORT": "alpha", "ORDER": "asc"}]),
               MEMBER_COLS)
        + file_out("tFileOutputDelimited_1", "C:/cscu/out/members.csv", MEMBER_COLS)
        + flow("tPostgresqlInput_1", "tSortRow_1")
        + flow("tSortRow_1", "tFileOutputDelimited_1", label="row2"))
    build("members_export_0.1.item", body)


def branch_balances():
    body = (
        pg_input("tPostgresqlInput_1",
                 'SELECT b.br_name AS "BR_NAME", a.bal_amt AS "BAL_AMT"\n'
                 'FROM cscu_core.accounts a JOIN cscu_core.branches b ON b.br_id = a.br_id',
                 BAL_COLS)
        + node("tAggregateRow", "tAggregateRow_1", 400, 100,
               table_param("GROUPBYS", [
                   {"OUTPUT_COLUMN": "BR_NAME", "INPUT_COLUMN": "BR_NAME"}])
               + table_param("OPERATIONS", [
                   {"OUTPUT_COLUMN": "TOTAL_BAL", "FUNCTION": "sum",
                    "INPUT_COLUMN": "BAL_AMT", "IGNORE_NULL": "false"},
                   {"OUTPUT_COLUMN": "ACCOUNTS", "FUNCTION": "count",
                    "INPUT_COLUMN": "BAL_AMT", "IGNORE_NULL": "false"}]),
               AGG_COLS)
        + file_out("tFileOutputDelimited_1", "C:/cscu/out/branch_balances.csv", AGG_COLS)
        + flow("tPostgresqlInput_1", "tAggregateRow_1")
        + flow("tAggregateRow_1", "tFileOutputDelimited_1", label="row2"))
    build("branch_balances_0.1.item", body)


def high_value_txns():
    body = (
        pg_input("tPostgresqlInput_1",
                 'SELECT t.txn_dt AS "TXN_DT", a.acct_no AS "ACCT_NO",\n'
                 '       t.txn_type_cd AS "TXN_TYPE_CD", t.txn_amt AS "TXN_AMT"\n'
                 'FROM cscu_core.transactions t JOIN cscu_core.accounts a ON a.acct_id = t.acct_id',
                 TXN_COLS)
        + node("tFilterRow", "tFilterRow_1", 400, 100,
               param("LOGICAL_OP", "&&")
               + param("USE_ADVANCED", "false", field="CHECK")
               + table_param("CONDITIONS", [
                   {"INPUT_COLUMN": "TXN_AMT", "FUNCTION": "", "OPERATOR": ">=",
                    "RVALUE": "10000"}]),
               TXN_COLS)
        + file_out("tFileOutputDelimited_1", "C:/cscu/out/high_value_txns.csv", TXN_COLS)
        + flow("tPostgresqlInput_1", "tFilterRow_1")
        + flow("tFilterRow_1", "tFileOutputDelimited_1", label="row2"))
    build("high_value_txns_0.1.item", body)


def nightly_orchestrator():
    def runjob(unique, process, x):
        return node("tRunJob", unique, x, 100,
                    param("PROCESS", process)
                    + param("PROCESS:PROCESS_TYPE_CONTEXT", "Default")
                    + param("TRANSMIT_WHOLE_CONTEXT", "true", field="CHECK"))

    body = (
        node("tPrejob", "tPrejob_1", 100, 20)
        + runjob("tRunJob_1", "members_export", 100)
        + runjob("tRunJob_2", "branch_balances", 400)
        + runjob("tRunJob_3", "high_value_txns", 700)
        + subjob_ok("tPrejob_1", "tRunJob_1")
        + subjob_ok("tRunJob_1", "tRunJob_2")
        + subjob_ok("tRunJob_2", "tRunJob_3"))
    build("cscu_nightly_0.1.item", body)


if __name__ == "__main__":
    members_export()
    branch_balances()
    high_value_txns()
    nightly_orchestrator()
