"""Generate the CSCU Crystal-migration ladder: six RptToXml-shaped dumps of
increasing complexity, all backed by the live cscu_core schema so each one
converts AND renders end-to-end against the real database.

These are authored dumps (not extracted from .rpt binaries) — the pipeline
consumes RptToXml XML, so no Crystal Reports Designer is needed to test the
converter. The 150-file GitHub corpus stays the parser's real-world variety
test; this ladder is the end-to-end render-and-verify / demo set.

Run:  python samples/crystal/ladder/build_ladder.py
"""

from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

OUT = Path(__file__).parent
TW = 20  # twips per point — parser divides by this

# ------------------------------------------------------------------ helpers

def _font(size, bold=False, align=None):
    a = f' HorizontalAlignment="{align}"' if align else ""
    return size, bold, a


def text(name, s, x, y, w, h, size=9, bold=False, align=None):
    a = f' HorizontalAlignment="{align}"' if align else ""
    return (f'<TextObject Name={quoteattr(name)} Text={quoteattr(s)} '
            f'Left="{x*TW}" Top="{y*TW}" Width="{w*TW}" Height="{h*TW}"{a}>'
            f'<Font FontName="Arial" Size="{size}" Bold="{str(bold).lower()}"/></TextObject>')


def field(name, ref, x, y, w, h, size=9, bold=False, align=None):
    a = f' HorizontalAlignment="{align}"' if align else ""
    return (f'<FieldObject Name={quoteattr(name)} DataSource={quoteattr(ref)} '
            f'Left="{x*TW}" Top="{y*TW}" Width="{w*TW}" Height="{h*TW}"{a}>'
            f'<Font FontName="Arial" Size="{size}" Bold="{str(bold).lower()}"/></FieldObject>')


def line(name, x, y, w):
    return (f'<LineObject Name={quoteattr(name)} Left="{x*TW}" Top="{y*TW}" '
            f'Width="{w*TW}" Height="20"/>')


def cond_color(inner):
    """A FontColorConditionFormulas element — surfaces as a conditional-format
    note (the parser flags these, it does not convert them)."""
    return (f'<FontColorConditionFormulas Color={quoteattr(inner)}/>')


def section(kind, name, height, objects, group_index=None, suppress=False):
    fmt = (f'<SectionFormat EnableSuppress="{str(suppress).lower()}"/>')
    return (f'<Area Kind="{kind}" Name="{name}Area">'
            f'<Sections><Section Name="{name}" Height="{int(height*TW)}">'
            f'{fmt}<ReportObjects>{"".join(objects)}</ReportObjects>'
            f'</Section></Sections></Area>')


def build(name, sql, fields, groups=None, formulas=None, params=None,
          summaries=None, record_selection=None, areas=None):
    parts = [f'<?xml version="1.0" encoding="utf-8"?>',
             f'<Report Name={quoteattr(name)} FileName={quoteattr(name + ".rpt")} HasSavedData="False">']
    # database
    field_xml = "".join(
        f'<Field Name="{c}" ValueType="{vt}"/>' for c, vt in fields)
    parts.append(
        '<Database><Tables>'
        '<Table Name="Command" Alias="Command" ClassName="CommandTable">'
        '<ConnectionInfo QE_DatabaseName="cscu_core" QE_DatabaseType="PostgreSQL" '
        'UserName="" Password=""/>'
        f'<Command>{escape(sql)}</Command>'
        f'<Fields>{field_xml}</Fields>'
        '</Table></Tables></Database>')
    # data definition
    dd = ['<DataDefinition>']
    if record_selection:
        dd.append(f'<RecordSelectionFormula>{escape(record_selection)}</RecordSelectionFormula>')
    dd.append('<Groups>' + "".join(
        f'<Group ConditionField="{{Command.{g}}}"/>' for g in (groups or [])) + '</Groups>')
    dd.append('<FormulaFieldDefinitions>' + "".join(
        f'<FormulaFieldDefinition Name="{fn}" FormulaName="{{@{fn}}}" ValueType="{vt}">{escape(body)}</FormulaFieldDefinition>'
        for fn, vt, body in (formulas or [])) + '</FormulaFieldDefinitions>')
    dd.append('<ParameterFieldDefinitions>' + "".join(
        f'<ParameterFieldDefinition Name="{pn}" ParameterFieldName="{{?{pn}}}" '
        f'ValueType="{vt}" PromptText={quoteattr(prompt)} DefaultValue={quoteattr(dv)}/>'
        for pn, vt, prompt, dv in (params or [])) + '</ParameterFieldDefinitions>')
    dd.append('<SummaryFields>' + "".join(
        (f'<SummaryFieldDefinition Name={quoteattr(sn)} Operation="{op}" '
         f'SummarizedField="{{Command.{col}}}"'
         + (f' Group="{{Command.{grp}}}"' if grp else '') + '/>')
        for sn, op, col, grp in (summaries or [])) + '</SummaryFields>')
    dd.append('</DataDefinition>')
    parts.append("".join(dd))
    # print options — real RptToXml shape (PageMargins child)
    parts.append(
        '<PrintOptions PaperOrientation="Landscape" PaperSize="PaperA4">'
        '<PageMargins topMargin="360" leftMargin="360" bottomMargin="360" rightMargin="360"/>'
        '</PrintOptions>')
    # report definition
    parts.append(f'<ReportDefinition><Areas>{"".join(areas)}</Areas></ReportDefinition>')
    parts.append('</Report>')
    (OUT / (name_to_file(name))).write_text("".join(parts), encoding="utf-8")


def name_to_file(name):
    return LADDER_FILES[name]


# rung -> filename
LADDER_FILES = {}


# ---------------------------------------------------------------- the ladder

def rung(idx, filename):
    def deco(fn):
        LADDER_FILES[fn.__name__] = filename
        return fn
    return deco


def page_footer():
    return section("PageFooter", "PF", 22, [
        field("PrintDate", "PrintDate", 0, 2, 120, 14, size=8),
        field("PageNum", "PageNumber", 640, 2, 100, 14, size=8, align="RightAlign"),
    ])


def header_band(title, cols):
    """ReportHeader with title + a PageHeader column label row."""
    rh = section("ReportHeader", "RH", 40, [
        text("Title", title, 0, 6, 700, 24, size=16, bold=True),
        line("Rule", 0, 34, 760),
    ])
    labels = []
    x = 0
    for label, _ref, w, align, _vt in cols:
        labels.append(text(f"h_{label}", label, x, 2, w, 16, size=9, bold=True, align=align))
        x += w
    ph = section("PageHeader", "PH", 20, labels)
    return rh, ph


def detail_band(cols, extra=None):
    objs = []
    x = 0
    for label, ref, w, align, _vt in cols:
        objs.append(field(f"d_{label}", ref, x, 0, w, 16, size=9, align=align))
        x += w
    objs.extend(extra or [])
    return section("Detail", "D", 18, objs)


# ---- Rung 1: Member Roster — single table, no groups/formulas ----
def build_r1():
    cols = [("Member #", "{Command.MBR_NO}", 90, None, "StringField"),
            ("First", "{Command.FIRST_NM}", 110, None, "StringField"),
            ("Last", "{Command.LAST_NM}", 130, None, "StringField"),
            ("City", "{Command.CITY}", 140, None, "StringField"),
            ("State", "{Command.ST}", 60, None, "StringField"),
            ("Status", "{Command.MBR_STATUS}", 90, None, "StringField")]
    rh, ph = header_band("CSCU Member Roster", cols)
    build("CSCU Member Roster",
          'SELECT mbr_no AS "MBR_NO", first_nm AS "FIRST_NM", last_nm AS "LAST_NM",\n'
          '       city AS "CITY", st AS "ST", mbr_status AS "MBR_STATUS"\n'
          'FROM cscu_core.members\nORDER BY last_nm, first_nm',
          fields=[("MBR_NO","StringField"),("FIRST_NM","StringField"),("LAST_NM","StringField"),
                  ("CITY","StringField"),("ST","StringField"),("MBR_STATUS","StringField")],
          areas=[rh, ph, detail_band(cols), page_footer()])


# ---- Rung 2: Accounts by Branch — one join, one group, sum summary ----
def build_r2():
    cols = [("Account #", "{Command.ACCT_NO}", 150, None, "StringField"),
            ("Type", "{Command.ACCT_TYPE_CD}", 120, None, "StringField"),
            ("Status", "{Command.ACCT_STATUS}", 120, None, "StringField"),
            ("Balance", "{Command.BAL_AMT}", 140, "RightAlign", "CurrencyField")]
    rh, ph = header_band("Accounts by Branch", cols)
    gh = section("GroupHeader", "GH", 22, [
        field("BranchName", "{Command.BR_NAME}", 0, 3, 400, 18, size=11, bold=True)], group_index=0)
    gf = section("GroupFooter", "GF", 20, [
        text("SubLbl", "Branch total:", 300, 2, 120, 16, size=9, bold=True),
        field("SubTot", "{#Sum of BAL_AMT}", 540, 2, 140, 16, size=9, bold=True, align="RightAlign")], group_index=0)
    rf = section("ReportFooter", "RF", 22, [
        text("GtLbl", "Grand total:", 300, 3, 120, 16, size=10, bold=True),
        field("GrandTot", "{#Grand Total BAL_AMT}", 540, 3, 140, 16, size=10, bold=True, align="RightAlign")])
    build("Accounts by Branch",
          'SELECT b.br_name AS "BR_NAME", a.acct_no AS "ACCT_NO",\n'
          '       a.acct_type_cd AS "ACCT_TYPE_CD", a.acct_status AS "ACCT_STATUS",\n'
          '       a.bal_amt AS "BAL_AMT"\n'
          'FROM cscu_core.accounts a\n'
          'JOIN cscu_core.branches b ON b.br_id = a.br_id\n'
          'ORDER BY b.br_name, a.acct_no',
          fields=[("BR_NAME","StringField"),("ACCT_NO","StringField"),("ACCT_TYPE_CD","StringField"),
                  ("ACCT_STATUS","StringField"),("BAL_AMT","CurrencyField")],
          groups=["BR_NAME"],
          summaries=[("Sum of BAL_AMT","Sum","BAL_AMT","BR_NAME"),
                     ("Grand Total BAL_AMT","Sum","BAL_AMT",None)],
          areas=[rh, ph, gh, detail_band(cols), gf, rf, page_footer()])


# ---- Rung 3: Transaction Register — multi-join via accounts, formulas ----
def build_r3():
    cols = [("Date", "{Command.TXN_DT}", 110, None, "DateField"),
            ("Account", "{Command.ACCT_NO}", 130, None, "StringField"),
            ("Member", "{@FullName}", 160, None, "StringField"),
            ("Type", "{Command.TXN_TYPE_CD}", 90, None, "StringField"),
            ("Merchant", "{Command.MERCH_NM}", 160, None, "StringField"),
            ("Amount", "{Command.TXN_AMT}", 110, "RightAlign", "CurrencyField")]
    rh, ph = header_band("Transaction Register by Branch", cols)
    gh = section("GroupHeader", "GH", 22, [
        field("BranchName", "{Command.BR_NAME}", 0, 3, 400, 18, size=11, bold=True)], group_index=0)
    detail_extra = [field("Flow", "{@FlowType}", 760, 0, 60, 16, size=9)]
    gf = section("GroupFooter", "GF", 20, [
        text("SubLbl", "Branch net:", 500, 2, 110, 16, size=9, bold=True),
        field("SubTot", "{#Sum of TXN_AMT}", 650, 2, 110, 16, size=9, bold=True, align="RightAlign")], group_index=0)
    rf = section("ReportFooter", "RF", 22, [
        text("GtLbl", "Net movement:", 500, 3, 130, 16, size=10, bold=True),
        field("GrandTot", "{#Grand Total TXN_AMT}", 650, 3, 110, 16, size=10, bold=True, align="RightAlign")])
    build("Transaction Register",
          'SELECT b.br_name AS "BR_NAME", t.txn_dt AS "TXN_DT", a.acct_no AS "ACCT_NO",\n'
          '       m.first_nm AS "FIRST_NM", m.last_nm AS "LAST_NM",\n'
          '       t.txn_type_cd AS "TXN_TYPE_CD", t.merch_nm AS "MERCH_NM", t.txn_amt AS "TXN_AMT"\n'
          'FROM cscu_core.transactions t\n'
          'JOIN cscu_core.accounts a ON a.acct_id = t.acct_id\n'
          'JOIN cscu_core.members  m ON m.mbr_id  = a.mbr_id\n'
          'JOIN cscu_core.branches b ON b.br_id   = a.br_id\n'
          'ORDER BY b.br_name, t.txn_dt',
          fields=[("BR_NAME","StringField"),("TXN_DT","DateField"),("ACCT_NO","StringField"),
                  ("FIRST_NM","StringField"),("LAST_NM","StringField"),("TXN_TYPE_CD","StringField"),
                  ("MERCH_NM","StringField"),("TXN_AMT","CurrencyField")],
          groups=["BR_NAME"],
          formulas=[("FullName","StringField","{Command.FIRST_NM} + ' ' + {Command.LAST_NM}"),
                    ("FlowType","StringField",'If {Command.TXN_AMT} < 0 Then "DR" Else "CR"')],
          summaries=[("Sum of TXN_AMT","Sum","TXN_AMT","BR_NAME"),
                     ("Grand Total TXN_AMT","Sum","TXN_AMT",None)],
          areas=[rh, ph, gh, detail_band(cols, detail_extra), gf, rf, page_footer()])


# ---- Rung 4: Member Statement — parameter, nested groups, running total ----
def build_r4():
    cols = [("Date", "{Command.TXN_DT}", 120, None, "DateField"),
            ("Type", "{Command.TXN_TYPE_CD}", 100, None, "StringField"),
            ("Merchant", "{Command.MERCH_NM}", 200, None, "StringField"),
            ("Amount", "{Command.TXN_AMT}", 120, "RightAlign", "CurrencyField"),
            ("Balance", "{@RunningBalance}", 120, "RightAlign", "NumberField")]
    rh, ph = header_band("Member Account Statement", cols)
    gh1 = section("GroupHeader", "GH1", 24, [
        field("MemberHdr", "{@FullName}", 0, 3, 400, 18, size=12, bold=True),
        field("MemberNo", "{Command.MBR_NO}", 420, 4, 150, 16, size=9)], group_index=0)
    gh2 = section("GroupHeader", "GH2", 20, [
        text("AcctLbl", "Account", 20, 2, 70, 16, size=9, bold=True),
        field("AcctNo", "{Command.ACCT_NO}", 90, 2, 160, 16, size=9, bold=True)], group_index=1)
    gf2 = section("GroupFooter", "GF2", 18, [
        text("AcctSubLbl", "Account total:", 420, 1, 120, 14, size=8, bold=True),
        field("AcctSub", "{#Sum of TXN_AMT}", 660, 1, 120, 14, size=8, bold=True, align="RightAlign")], group_index=1)
    build("Member Statement",
          'SELECT m.mbr_no AS "MBR_NO", m.first_nm AS "FIRST_NM", m.last_nm AS "LAST_NM",\n'
          '       a.acct_no AS "ACCT_NO", t.txn_dt AS "TXN_DT", t.txn_type_cd AS "TXN_TYPE_CD",\n'
          '       t.merch_nm AS "MERCH_NM", t.txn_amt AS "TXN_AMT"\n'
          'FROM cscu_core.transactions t\n'
          'JOIN cscu_core.accounts a ON a.acct_id = t.acct_id\n'
          'JOIN cscu_core.members  m ON m.mbr_id  = a.mbr_id\n'
          'ORDER BY m.mbr_no, a.acct_no, t.txn_dt',
          fields=[("MBR_NO","StringField"),("FIRST_NM","StringField"),("LAST_NM","StringField"),
                  ("ACCT_NO","StringField"),("TXN_DT","DateField"),("TXN_TYPE_CD","StringField"),
                  ("MERCH_NM","StringField"),("TXN_AMT","CurrencyField")],
          groups=["MBR_NO","ACCT_NO"],
          params=[("MemberNo","StringField","Member number","")],
          record_selection="{Command.MBR_NO} = {?MemberNo}",
          formulas=[("FullName","StringField","{Command.FIRST_NM} + ' ' + {Command.LAST_NM}"),
                    ("RunningBalance","NumberField",
                     "WhilePrintingRecords;\nShared NumberVar bal;\nbal := bal + {Command.TXN_AMT};\nbal")],
          summaries=[("Sum of TXN_AMT","Sum","TXN_AMT","ACCT_NO")],
          areas=[rh, ph, gh1, gh2, detail_band(cols), gf2, page_footer()])


# ---- Rung 5: Loan Portfolio — conditional formatting + unsupported aggregate ----
def build_r5():
    cols = [("Loan #", "{Command.LN_NO}", 130, None, "StringField"),
            ("Type", "{Command.LN_TYPE_CD}", 100, None, "StringField"),
            ("Original", "{Command.ORIG_AMT}", 130, "RightAlign", "CurrencyField"),
            ("Balance", "{Command.PRIN_BAL_AMT}", 130, "RightAlign", "CurrencyField"),
            ("APR %", "{Command.APR_RT}", 90, "RightAlign", "NumberField"),
            ("Status", "{Command.LN_STATUS}", 110, None, "StringField")]
    rh, ph = header_band("Loan Portfolio by Branch", cols)
    gh = section("GroupHeader", "GH", 22, [
        field("BranchName", "{Command.BR_NAME}", 0, 3, 400, 18, size=11, bold=True)], group_index=0)
    # a detail balance field with a conditional font-color formula (delinquent = red)
    bal_field = (f'<FieldObject Name="d_Balance" DataSource="{{Command.PRIN_BAL_AMT}}" '
                 f'Left="{460*TW}" Top="0" Width="{130*TW}" Height="{16*TW}" HorizontalAlignment="RightAlign">'
                 f'<Font FontName="Arial" Size="9"/>'
                 f'{cond_color("If {Command.LN_STATUS} = \'Delinquent\' Then crRed Else crBlack")}'
                 f'</FieldObject>')
    detail_cols = [c for c in cols if c[0] != "Balance"]
    detail = section("Detail", "D", 18,
        [field(f"d_{lbl}", ref, sum(w for _,_,w,_,_ in cols[:i]), 0, w, 16, size=9, align=al)
         for i,(lbl,ref,w,al,_vt) in enumerate(cols) if lbl != "Balance"] + [bal_field])
    gf = section("GroupFooter", "GF", 36, [
        text("SumLbl", "Portfolio balance:", 300, 2, 150, 14, size=8, bold=True),
        field("SumBal", "{#Sum of PRIN_BAL_AMT}", 460, 2, 130, 14, size=8, bold=True, align="RightAlign"),
        text("AvgLbl", "Avg APR:", 300, 18, 150, 14, size=8),
        field("AvgApr", "{#Average of APR_RT}", 460, 18, 130, 14, size=8, align="RightAlign"),
        text("SdLbl", "APR std dev:", 620, 18, 100, 14, size=8),
        field("SdApr", "{#StdDev of APR_RT}", 720, 18, 100, 14, size=8, align="RightAlign")], group_index=0)
    build("Loan Portfolio",
          'SELECT b.br_name AS "BR_NAME", l.ln_no AS "LN_NO", l.ln_type_cd AS "LN_TYPE_CD",\n'
          '       l.orig_amt AS "ORIG_AMT", l.prin_bal_amt AS "PRIN_BAL_AMT",\n'
          '       l.apr_rt AS "APR_RT", l.ln_status AS "LN_STATUS"\n'
          'FROM cscu_core.loans l\n'
          'JOIN cscu_core.members  m ON m.mbr_id = l.mbr_id\n'
          'JOIN cscu_core.branches b ON b.br_id  = m.br_id\n'
          'ORDER BY b.br_name, l.ln_no',
          fields=[("BR_NAME","StringField"),("LN_NO","StringField"),("LN_TYPE_CD","StringField"),
                  ("ORIG_AMT","CurrencyField"),("PRIN_BAL_AMT","CurrencyField"),
                  ("APR_RT","NumberField"),("LN_STATUS","StringField")],
          groups=["BR_NAME"],
          summaries=[("Sum of PRIN_BAL_AMT","Sum","PRIN_BAL_AMT","BR_NAME"),
                     ("Average of APR_RT","Average","APR_RT","BR_NAME"),
                     ("StdDev of APR_RT","StdDeviation","APR_RT","BR_NAME")],
          areas=[rh, ph, gh, detail, gf, page_footer()])


# ---- Rung 6: Suspicious Activity — subreport, image, cross-tab TODOs ----
def build_r6():
    cols = [("Filed", "{Command.FILED_DT}", 110, None, "DateField"),
            ("Member", "{@FullName}", 170, None, "StringField"),
            ("Activity", "{Command.ACTIVITY_TYPE_CD}", 150, None, "StringField"),
            ("Amount", "{Command.SAR_AMT}", 120, "RightAlign", "CurrencyField"),
            ("Status", "{Command.SAR_STATUS}", 120, None, "StringField")]
    rh0 = section("ReportHeader", "RH", 70, [
        text("Title", "Suspicious Activity Report (SAR)", 0, 6, 700, 24, size=16, bold=True),
        '<PictureObject Name="Logo" Left="0" Top="720" Width="2400" Height="600"/>',
        line("Rule", 0, 64, 900),
    ])
    labels = []
    x = 0
    for label, _ref, w, align, _vt in cols:
        labels.append(text(f"h_{label}", label, x, 2, w, 16, size=9, bold=True, align=align))
        x += w
    ph = section("PageHeader", "PH", 20, labels)
    detail_extra = ['<SubreportObject Name="NarrativeSub" SubreportName="sar_narrative" '
                    f'Left="0" Top="{18*TW}" Width="{900*TW}" Height="{40*TW}"/>']
    rf = section("ReportFooter", "RF", 60, [
        '<CrossTabObject Name="ActivityPivot" Left="0" Top="200" Width="9000" Height="1000"/>',
        text("Note", "Activity type x status pivot (rebuild as PRD crosstab)", 0, 2, 500, 14, size=8),
    ])
    build("Suspicious Activity Report",
          'SELECT s.filed_dt AS "FILED_DT", m.first_nm AS "FIRST_NM", m.last_nm AS "LAST_NM",\n'
          '       s.activity_type_cd AS "ACTIVITY_TYPE_CD", s.sar_amt AS "SAR_AMT",\n'
          '       s.sar_status AS "SAR_STATUS", s.narrative_txt AS "NARRATIVE_TXT"\n'
          'FROM cscu_core.suspicious_activity s\n'
          'JOIN cscu_core.members m ON m.mbr_id = s.mbr_id\n'
          'ORDER BY s.filed_dt',
          fields=[("FILED_DT","DateField"),("FIRST_NM","StringField"),("LAST_NM","StringField"),
                  ("ACTIVITY_TYPE_CD","StringField"),("SAR_AMT","CurrencyField"),
                  ("SAR_STATUS","StringField"),("NARRATIVE_TXT","StringField")],
          formulas=[("FullName","StringField","{Command.FIRST_NM} + ' ' + {Command.LAST_NM}")],
          areas=[rh0, ph, detail_band(cols, detail_extra), rf, page_footer()])


LADDER_FILES.update({
    "build_r1": "01_member_roster.xml",
    "build_r2": "02_accounts_by_branch.xml",
    "build_r3": "03_transaction_register.xml",
    "build_r4": "04_member_statement.xml",
    "build_r5": "05_loan_portfolio.xml",
    "build_r6": "06_suspicious_activity.xml",
})
# map report display names to files
_NAME_TO_FILE = {
    "CSCU Member Roster": "01_member_roster.xml",
    "Accounts by Branch": "02_accounts_by_branch.xml",
    "Transaction Register": "03_transaction_register.xml",
    "Member Statement": "04_member_statement.xml",
    "Loan Portfolio": "05_loan_portfolio.xml",
    "Suspicious Activity Report": "06_suspicious_activity.xml",
}


def name_to_file(name):  # noqa: F811 — override with the real map
    return _NAME_TO_FILE[name]


if __name__ == "__main__":
    for fn in (build_r1, build_r2, build_r3, build_r4, build_r5, build_r6):
        fn()
    for f in sorted(OUT.glob("*.xml")):
        print("wrote", f.name)
