"""Generate the CSCU Crystal-migration ladder: six RptToXml-shaped dumps of
increasing complexity, backed by the live cscu_core schema so each converts
AND renders end-to-end. Styled as polished, professional credit-union reports
using the SAME formatting elements real RptToXml emits — nested <Color>,
<BackgroundColor>, <Border> line styles, and a base64 <ImageData> logo — so
the polish is genuinely carried from the "Crystal source" through conversion,
not injected by the writer.

Run:  python samples/cr_demo/build_ladder.py
"""

import base64
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

OUT = Path(__file__).parent
TW = 20  # twips per point

# ---- CSCU professional theme -------------------------------------------------
NAVY = (19, 51, 70)      # #133346
GOLD = (201, 162, 74)    # #c9a24a
SLATE = (91, 119, 141)   # #5b778d
LIGHT = (238, 241, 244)  # #eef1f4  band fill
WHITE = (255, 255, 255)
INK = (34, 40, 46)       # #22282e
LOGO_B64 = (OUT / "cscu_logo.b64").read_text().strip() if (OUT / "cscu_logo.b64").exists() else ""


def _color_el(tag, rgb):
    r, g, b = rgb
    return f'<{tag} Name="c" A="255" R="{r}" G="{g}" B="{b}" />'


def _border(color=None, sides="Bottom"):
    styles = {s: ("SingleLine" if s in sides else "NoLine")
              for s in ("Top", "Bottom", "Left", "Right")}
    attrs = " ".join(f'{s}LineStyle="{styles[s]}"' for s in ("Top", "Bottom", "Left", "Right"))
    inner = _color_el("BorderColor", color) if color else ""
    return f'<Border {attrs} HasDropShadow="False">{inner}</Border>'


def obj(kind, name, x, y, w, h, *, text=None, ref=None, size=9, bold=False,
        align=None, valign="middle", color=None, bg=None, border=None,
        border_sides="Bottom"):
    a = f' HorizontalAlignment="{align}"' if align else ""
    va = f' VerticalAlignment="{valign}"' if valign else ""
    extra = f' Text={quoteattr(text)}' if text is not None else ""
    extra += f' DataSource={quoteattr(ref)}' if ref is not None else ""
    children = [f'<Font FontName="Arial" Size="{size}" Bold="{str(bold).lower()}"/>']
    if color:
        children.append(_color_el("Color", color))
    if bg:
        children.append(_color_el("BackgroundColor", bg))
    if border:
        children.append(_border(border, border_sides))
    return (f'<{kind} Name={quoteattr(name)}{extra} '
            f'Left="{x*TW}" Top="{y*TW}" Width="{w*TW}" Height="{h*TW}"{a}{va}>'
            f'{"".join(children)}</{kind}>')


def text(name, s, x, y, w, h, **kw):
    return obj("TextObject", name, x, y, w, h, text=s, **kw)


def field(name, ref, x, y, w, h, **kw):
    return obj("FieldObject", name, x, y, w, h, ref=ref, **kw)


def box(name, x, y, w, h, fill):
    return (f'<BoxObject Name={quoteattr(name)} Left="{x*TW}" Top="{y*TW}" '
            f'Width="{w*TW}" Height="{h*TW}">{_color_el("BackgroundColor", fill)}'
            f'{_border(fill, sides="")}</BoxObject>')


def logo(name, x, y, w, h):
    data = f'<ImageData>{LOGO_B64}</ImageData>' if LOGO_B64 else ""
    return (f'<PictureObject Name={quoteattr(name)} Left="{x*TW}" Top="{y*TW}" '
            f'Width="{w*TW}" Height="{h*TW}">{data}</PictureObject>')


def chart(name, x, y, w, h, style, title, category, value):
    """A ChartObject shaped like the forked extractor's emission."""
    return (f'<ChartObject Name={quoteattr(name)} Left="{x*TW}" Top="{y*TW}" '
            f'Width="{w*TW}" Height="{h*TW}">'
            f'<ChartDefinition StyleType="crChartStyleType{style}" ChartType="crChartTypeGroup" '
            f'Title={quoteattr(title)} Subtitle="">'
            f'<ConditionFields><Field FormulaName="{{Command.{category}}}" Name="{category}"/></ConditionFields>'
            f'<DataFields><Field FormulaName="Sum ({{Command.{value}}})" Name="{value}"/></DataFields>'
            f'</ChartDefinition></ChartObject>')


def section(kind, name, height, objects, bg=None):
    fill = _color_el("BackgroundColor", bg) if bg else ""
    fmt = f'<SectionFormat EnableSuppress="false">{fill}</SectionFormat>'
    return (f'<Area Kind="{kind}" Name="{name}Area"><Sections>'
            f'<Section Name="{name}" Height="{int(height*TW)}">{fmt}'
            f'<ReportObjects>{"".join(objects)}</ReportObjects></Section>'
            f'</Sections></Area>')


# ---- report skeleton ---------------------------------------------------------

_NAME_TO_FILE = {}


def build(name, filename, sql, fields, *, groups=None, formulas=None, params=None,
          summaries=None, record_selection=None, areas):
    _NAME_TO_FILE[name] = filename
    p = [f'<?xml version="1.0" encoding="utf-8"?>',
         f'<Report Name={quoteattr(name)} FileName={quoteattr(name + ".rpt")} HasSavedData="False">']
    fx = "".join(f'<Field Name="{c}" ValueType="{vt}"/>' for c, vt in fields)
    p.append('<Database><Tables>'
             '<Table Name="Command" Alias="Command" ClassName="CommandTable">'
             '<ConnectionInfo QE_DatabaseName="cscu_core" QE_DatabaseType="PostgreSQL" UserName="" Password=""/>'
             f'<Command>{escape(sql)}</Command><Fields>{fx}</Fields></Table></Tables></Database>')
    dd = ['<DataDefinition>']
    if record_selection:
        dd.append(f'<RecordSelectionFormula>{escape(record_selection)}</RecordSelectionFormula>')
    dd.append('<Groups>' + "".join(f'<Group ConditionField="{{Command.{g}}}"/>' for g in (groups or [])) + '</Groups>')
    dd.append('<FormulaFieldDefinitions>' + "".join(
        f'<FormulaFieldDefinition Name="{fn}" FormulaName="{{@{fn}}}" ValueType="{vt}">{escape(b)}</FormulaFieldDefinition>'
        for fn, vt, b in (formulas or [])) + '</FormulaFieldDefinitions>')
    dd.append('<ParameterFieldDefinitions>' + "".join(
        f'<ParameterFieldDefinition Name="{pn}" ParameterFieldName="{{?{pn}}}" ValueType="{vt}" '
        f'PromptText={quoteattr(pr)} DefaultValue={quoteattr(dv)}/>' for pn, vt, pr, dv in (params or [])) +
        '</ParameterFieldDefinitions>')
    dd.append('<SummaryFields>' + "".join(
        (f'<SummaryFieldDefinition Name={quoteattr(sn)} Operation="{op}" SummarizedField="{{Command.{col}}}"'
         + (f' Group="{{Command.{grp}}}"' if grp else '') + '/>')
        for sn, op, col, grp in (summaries or [])) + '</SummaryFields>')
    dd.append('</DataDefinition>')
    p.append("".join(dd))
    p.append('<PrintOptions PaperOrientation="Landscape" PaperSize="PaperA4">'
             '<PageMargins topMargin="360" leftMargin="360" bottomMargin="360" rightMargin="360"/></PrintOptions>')
    p.append(f'<ReportDefinition><Areas>{"".join(areas)}</Areas></ReportDefinition></Report>')
    (OUT / filename).write_text("".join(p), encoding="utf-8")


# ---- shared professional bands ----------------------------------------------

def masthead(title, subtitle):
    """Navy report-header band with logo, white title, gold subtitle + rule."""
    return section("ReportHeader", "RH", 58, [
        logo("Logo", 8, 6, 120, 44),
        text("Title", title, 150, 8, 400, 26, size=18, bold=True, color=WHITE),
        text("Sub", subtitle, 152, 34, 560, 16, size=10, color=GOLD),
        text("Org", "Copperstate Credit Union", 556, 10, 244, 16, size=9,
             color=WHITE, align="RightAlign"),
        box("GoldRule", 0, 55, 806, 2, GOLD),
    ], bg=NAVY)


def column_header(cols):
    """Dark column-label row with white bold labels and a bottom border."""
    labels, x = [], 0
    for label, _ref, w, align, _vt in cols:
        labels.append(text(f"h_{label}", label, x, 2, w, 18, size=9, bold=True,
                           color=WHITE, align=align, border=SLATE))
        x += w
    return section("PageHeader", "PH", 22, labels, bg=NAVY)


def detail(cols, extra=None, zebra=False):
    objs, x = [], 0
    for label, ref, w, align, vt in cols:
        objs.append(field(f"d_{label}", ref, x, 0, w, 15, size=9, align=align, color=INK))
        x += w
    objs.extend(extra or [])
    return section("Detail", "D", 17, objs)


def group_header(ref, extra=None):
    return section("GroupHeader", "GH", 22, [
        box("GhBar", 0, 0, 806, 20, LIGHT),
        field("GroupVal", ref, 6, 2, 500, 17, size=11, bold=True, color=NAVY),
        *(extra or []),
    ])


def totals_footer(kind, name, label, ref, size=9, big=False):
    return section(kind, name, 22, [
        box("TotRule", 500, 0, 306, 1, GOLD),
        text(f"{name}Lbl", label, 500, 3, 150, 16, size=size, bold=True, color=NAVY),
        field(f"{name}Val", ref, 660, 3, 130, 16, size=size, bold=True,
              color=(GOLD if big else NAVY), align="RightAlign"),
    ])


def page_footer():
    return section("PageFooter", "PF", 22, [
        box("PfRule", 0, 0, 806, 1, SLATE),
        field("PrintDate", "PrintDate", 0, 4, 200, 14, size=8, color=SLATE),
        text("Conf", "Confidential — Copperstate Credit Union", 300, 4, 320, 14,
             size=8, color=SLATE, align="HorizontalCenterAlign"),
        field("PageNum", "PageNumber", 700, 4, 100, 14, size=8, color=SLATE, align="RightAlign"),
    ])


# ---- the six rungs ----------------------------------------------------------

def r1():
    cols = [("Member #", "{Command.MBR_NO}", 90, None, "StringField"),
            ("First", "{Command.FIRST_NM}", 110, None, "StringField"),
            ("Last", "{Command.LAST_NM}", 130, None, "StringField"),
            ("City", "{Command.CITY}", 150, None, "StringField"),
            ("State", "{Command.ST}", 70, "HorizontalCenterAlign", "StringField"),
            ("Status", "{Command.MBR_STATUS}", 100, None, "StringField")]
    build("CSCU Member Roster - Basic Layout", "01_member_roster.xml",
          'SELECT mbr_no AS "MBR_NO", first_nm AS "FIRST_NM", last_nm AS "LAST_NM",\n'
          '       city AS "CITY", st AS "ST", mbr_status AS "MBR_STATUS"\n'
          'FROM cscu_core.members\nORDER BY last_nm, first_nm',
          [("MBR_NO","StringField"),("FIRST_NM","StringField"),("LAST_NM","StringField"),
           ("CITY","StringField"),("ST","StringField"),("MBR_STATUS","StringField")],
          areas=[masthead("Member Roster", "Demo: basic layout, page bands"),
                 column_header(cols), detail(cols), page_footer()])


def r2():
    cols = [("Account #", "{Command.ACCT_NO}", 150, None, "StringField"),
            ("Type", "{Command.ACCT_TYPE_CD}", 120, None, "StringField"),
            ("Status", "{Command.ACCT_STATUS}", 120, None, "StringField"),
            ("Balance", "{Command.BAL_AMT}", 150, "RightAlign", "CurrencyField")]
    build("Accounts by Branch - Groups & Chart", "02_accounts_by_branch.xml",
          'SELECT b.br_name AS "BR_NAME", a.acct_no AS "ACCT_NO", a.acct_type_cd AS "ACCT_TYPE_CD",\n'
          '       a.acct_status AS "ACCT_STATUS", a.bal_amt AS "BAL_AMT"\n'
          'FROM cscu_core.accounts a JOIN cscu_core.branches b ON b.br_id = a.br_id\n'
          'ORDER BY b.br_name, a.acct_no',
          [("BR_NAME","StringField"),("ACCT_NO","StringField"),("ACCT_TYPE_CD","StringField"),
           ("ACCT_STATUS","StringField"),("BAL_AMT","CurrencyField")],
          groups=["BR_NAME"],
          summaries=[("Sum of BAL_AMT","Sum","BAL_AMT","BR_NAME"),
                     ("Grand Total BAL_AMT","Sum","BAL_AMT",None)],
          areas=[masthead("Accounts by Branch", "Demo: groups, totals and a migrated chart"),
                 column_header(cols), group_header("{Command.BR_NAME}"), detail(cols),
                 totals_footer("GroupFooter","GF","Branch total:","{#Sum of BAL_AMT}"),
                 section("ReportFooter", "RF", 262, [
                     box("RfRule", 500, 0, 306, 1, GOLD),
                     text("GtLbl", "Grand total:", 500, 3, 150, 16, size=10, bold=True, color=NAVY),
                     field("GtVal", "{#Grand Total BAL_AMT}", 660, 3, 130, 16, size=10,
                           bold=True, color=GOLD, align="RightAlign"),
                     chart("BalChart", 40, 26, 560, 230, "Bar",
                           "Deposit balances by branch", "BR_NAME", "BAL_AMT"),
                 ]),
                 page_footer()])


def r3():
    cols = [("Date", "{Command.TXN_DT}", 110, None, "DateField"),
            ("Account", "{Command.ACCT_NO}", 130, None, "StringField"),
            ("Member", "{@FullName}", 160, None, "StringField"),
            ("Type", "{Command.TXN_TYPE_CD}", 80, None, "StringField"),
            ("Merchant", "{Command.MERCH_NM}", 170, None, "StringField"),
            ("Amount", "{Command.TXN_AMT}", 120, "RightAlign", "CurrencyField")]
    extra = [field("Flow", "{@FlowType}", 756, 0, 50, 15, size=9,
                   align="HorizontalCenterAlign", color=SLATE)]
    build("Transaction Register - Formulas", "03_transaction_register.xml",
          'SELECT b.br_name AS "BR_NAME", t.txn_dt AS "TXN_DT", a.acct_no AS "ACCT_NO",\n'
          '       m.first_nm AS "FIRST_NM", m.last_nm AS "LAST_NM", t.txn_type_cd AS "TXN_TYPE_CD",\n'
          '       t.merch_nm AS "MERCH_NM", t.txn_amt AS "TXN_AMT"\n'
          'FROM cscu_core.transactions t\n'
          'JOIN cscu_core.accounts a ON a.acct_id = t.acct_id\n'
          'JOIN cscu_core.members  m ON m.mbr_id  = a.mbr_id\n'
          'JOIN cscu_core.branches b ON b.br_id   = a.br_id\n'
          'ORDER BY b.br_name, t.txn_dt',
          [("BR_NAME","StringField"),("TXN_DT","DateField"),("ACCT_NO","StringField"),
           ("FIRST_NM","StringField"),("LAST_NM","StringField"),("TXN_TYPE_CD","StringField"),
           ("MERCH_NM","StringField"),("TXN_AMT","CurrencyField")],
          groups=["BR_NAME"],
          formulas=[("FullName","StringField","{Command.FIRST_NM} + ' ' + {Command.LAST_NM}"),
                    ("FlowType","StringField",'If {Command.TXN_AMT} < 0 Then "DR" Else "CR"')],
          summaries=[("Sum of TXN_AMT","Sum","TXN_AMT","BR_NAME"),
                     ("Grand Total TXN_AMT","Sum","TXN_AMT",None)],
          areas=[masthead("Transaction Register", "Demo: multi-join SQL and translated formulas"),
                 column_header(cols), group_header("{Command.BR_NAME}"), detail(cols, extra),
                 totals_footer("GroupFooter","GF","Branch net:","{#Sum of TXN_AMT}"),
                 totals_footer("ReportFooter","RF","Net movement:","{#Grand Total TXN_AMT}",size=10,big=True),
                 page_footer()])


def r4():
    cols = [("Date", "{Command.TXN_DT}", 120, None, "DateField"),
            ("Type", "{Command.TXN_TYPE_CD}", 100, None, "StringField"),
            ("Merchant", "{Command.MERCH_NM}", 220, None, "StringField"),
            ("Amount", "{Command.TXN_AMT}", 120, "RightAlign", "CurrencyField"),
            ("Balance", "{@RunningBalance}", 120, "RightAlign", "NumberField")]
    gh1 = section("GroupHeader", "GH1", 26, [
        box("M1", 0, 0, 806, 24, NAVY),
        field("MemberHdr", "{@FullName}", 8, 3, 400, 18, size=12, bold=True, color=WHITE),
        field("MemberNo", "{Command.MBR_NO}", 606, 4, 200, 16, size=9, color=GOLD, align="RightAlign")])
    gh2 = section("GroupHeader", "GH2", 20, [
        text("AcctLbl", "Account", 20, 2, 70, 16, size=9, bold=True, color=SLATE),
        field("AcctNo", "{Command.ACCT_NO}", 90, 2, 160, 16, size=9, bold=True, color=NAVY)])
    build("Member Statement - Nested Groups & Running Total", "04_member_statement.xml",
          'SELECT m.mbr_no AS "MBR_NO", m.first_nm AS "FIRST_NM", m.last_nm AS "LAST_NM",\n'
          '       a.acct_no AS "ACCT_NO", t.txn_dt AS "TXN_DT", t.txn_type_cd AS "TXN_TYPE_CD",\n'
          '       t.merch_nm AS "MERCH_NM", t.txn_amt AS "TXN_AMT"\n'
          'FROM cscu_core.transactions t\n'
          'JOIN cscu_core.accounts a ON a.acct_id = t.acct_id\n'
          'JOIN cscu_core.members  m ON m.mbr_id  = a.mbr_id\n'
          'ORDER BY m.mbr_no, a.acct_no, t.txn_dt',
          [("MBR_NO","StringField"),("FIRST_NM","StringField"),("LAST_NM","StringField"),
           ("ACCT_NO","StringField"),("TXN_DT","DateField"),("TXN_TYPE_CD","StringField"),
           ("MERCH_NM","StringField"),("TXN_AMT","CurrencyField")],
          groups=["MBR_NO","ACCT_NO"],
          params=[("MemberNo","StringField","Member number","CSCU-100501")],
          record_selection="{Command.MBR_NO} = {?MemberNo}",
          formulas=[("FullName","StringField","{Command.FIRST_NM} + ' ' + {Command.LAST_NM}"),
                    ("RunningBalance","NumberField",
                     "WhilePrintingRecords;\nShared NumberVar bal;\nbal := bal + {Command.TXN_AMT};\nbal")],
          summaries=[("Sum of TXN_AMT","Sum","TXN_AMT","ACCT_NO")],
          areas=[masthead("Member Account Statement", "Demo: nested groups and an auto-rewritten running total"),
                 column_header(cols), gh1, gh2, detail(cols),
                 totals_footer("GroupFooter","GF2","Account total:","{#Sum of TXN_AMT}",size=8),
                 page_footer()])


def r5():
    cols = [("Loan #", "{Command.LN_NO}", 130, None, "StringField"),
            ("Type", "{Command.LN_TYPE_CD}", 100, None, "StringField"),
            ("Original", "{Command.ORIG_AMT}", 130, "RightAlign", "CurrencyField"),
            ("Balance", "{Command.PRIN_BAL_AMT}", 130, "RightAlign", "CurrencyField"),
            ("APR %", "{Command.APR_RT}", 90, "RightAlign", "NumberField"),
            ("Status", "{Command.LN_STATUS}", 110, None, "StringField")]
    # detail with a conditional font-color on the balance (delinquent = red)
    det = []
    x = 0
    for lbl, ref, w, al, vt in cols:
        if lbl == "Balance":
            det.append('<FieldObject Name="d_Balance" DataSource="{Command.PRIN_BAL_AMT}" '
                       f'Left="{x*TW}" Top="0" Width="{w*TW}" Height="{15*TW}" HorizontalAlignment="RightAlign">'
                       '<Font FontName="Arial" Size="9"/>'
                       '<FontColorConditionFormulas Color="If {Command.LN_STATUS} = \'Delinquent\' Then crRed Else crBlack"/>'
                       '</FieldObject>')
        else:
            det.append(field(f"d_{lbl}", ref, x, 0, w, 15, size=9, align=al, color=INK))
        x += w
    gf = section("GroupFooter", "GF", 40, [
        box("Rule", 300, 0, 506, 1, GOLD),
        text("SumLbl", "Portfolio balance:", 300, 3, 150, 14, size=8, bold=True, color=NAVY),
        field("SumBal", "{#Sum of PRIN_BAL_AMT}", 460, 3, 130, 14, size=8, bold=True, color=NAVY, align="RightAlign"),
        text("AvgLbl", "Avg APR:", 300, 20, 150, 14, size=8, color=SLATE),
        field("AvgApr", "{#Average of APR_RT}", 460, 20, 130, 14, size=8, color=SLATE, align="RightAlign"),
        text("SdLbl", "APR std dev:", 620, 20, 100, 14, size=8, color=SLATE),
        field("SdApr", "{#StdDev of APR_RT}", 716, 20, 90, 14, size=8, color=SLATE, align="RightAlign")])
    build("Loan Portfolio - Conditional Formatting", "05_loan_portfolio.xml",
          'SELECT b.br_name AS "BR_NAME", l.ln_no AS "LN_NO", l.ln_type_cd AS "LN_TYPE_CD",\n'
          '       l.orig_amt AS "ORIG_AMT", l.prin_bal_amt AS "PRIN_BAL_AMT",\n'
          '       l.apr_rt AS "APR_RT", l.ln_status AS "LN_STATUS"\n'
          'FROM cscu_core.loans l JOIN cscu_core.members m ON m.mbr_id = l.mbr_id\n'
          'JOIN cscu_core.branches b ON b.br_id = m.br_id\nORDER BY b.br_name, l.ln_no',
          [("BR_NAME","StringField"),("LN_NO","StringField"),("LN_TYPE_CD","StringField"),
           ("ORIG_AMT","CurrencyField"),("PRIN_BAL_AMT","CurrencyField"),
           ("APR_RT","NumberField"),("LN_STATUS","StringField")],
          groups=["BR_NAME"],
          summaries=[("Sum of PRIN_BAL_AMT","Sum","PRIN_BAL_AMT","BR_NAME"),
                     ("Average of APR_RT","Average","APR_RT","BR_NAME"),
                     ("StdDev of APR_RT","StdDeviation","APR_RT","BR_NAME")],
          areas=[masthead("Loan Portfolio", "Demo: conditional formatting and unsupported-aggregate flags"),
                 column_header(cols), group_header("{Command.BR_NAME}"),
                 section("Detail", "D", 17, det), gf, page_footer()])


def r6():
    cols = [("Filed", "{Command.FILED_DT}", 110, None, "DateField"),
            ("Member", "{@FullName}", 170, None, "StringField"),
            ("Activity", "{Command.ACTIVITY_TYPE_CD}", 150, None, "StringField"),
            ("Amount", "{Command.SAR_AMT}", 120, "RightAlign", "CurrencyField"),
            ("Status", "{Command.SAR_STATUS}", 120, None, "StringField")]
    extra = ['<SubreportObject Name="NarrativeSub" SubreportName="sar_narrative" '
             f'Left="0" Top="{17*TW}" Width="{806*TW}" Height="{36*TW}"/>']
    rf = section("ReportFooter", "RF", 60, [
        box("PivotBar", 0, 0, 806, 1, GOLD),
        '<CrossTabObject Name="ActivityPivot" Left="0" Top="200" Width="8060" Height="1000"/>',
        text("Note", "Activity type x status pivot (rebuild as PRD crosstab)", 0, 4, 500, 14,
             size=8, color=SLATE)])
    build("Suspicious Activity - Subreport & Cross-tab", "06_suspicious_activity.xml",
          'SELECT s.filed_dt AS "FILED_DT", m.first_nm AS "FIRST_NM", m.last_nm AS "LAST_NM",\n'
          '       s.activity_type_cd AS "ACTIVITY_TYPE_CD", s.sar_amt AS "SAR_AMT",\n'
          '       s.sar_status AS "SAR_STATUS", s.narrative_txt AS "NARRATIVE_TXT"\n'
          'FROM cscu_core.suspicious_activity s JOIN cscu_core.members m ON m.mbr_id = s.mbr_id\n'
          'ORDER BY s.filed_dt',
          [("FILED_DT","DateField"),("FIRST_NM","StringField"),("LAST_NM","StringField"),
           ("ACTIVITY_TYPE_CD","StringField"),("SAR_AMT","CurrencyField"),
           ("SAR_STATUS","StringField"),("NARRATIVE_TXT","StringField")],
          formulas=[("FullName","StringField","{Command.FIRST_NM} + ' ' + {Command.LAST_NM}")],
          areas=[masthead("Suspicious Activity Report (SAR)", "Demo: subreport, image and cross-tab TODO placeholders"),
                 column_header(cols), detail(cols, extra), rf, page_footer()])


def flagship():
    """The UI 'Try the Crystal sample' report: professionally styled, and rich
    enough to show every conversion outcome (auto + manual formulas, summaries,
    a parameter). Written to ../branch_transactions.xml."""
    cols = [("Date", "{Command.TXN_DATE}", 105, None, "DateField"),
            ("Account", "{Command.ACCOUNT_ID}", 120, None, "StringField"),
            ("Member", "{@FullName}", 150, None, "StringField"),
            ("Type", "{Command.TXN_TYPE}", 80, None, "StringField"),
            ("Amount", "{Command.AMOUNT}", 115, "RightAlign", "CurrencyField"),
            ("Risk", "{@RiskFlag}", 70, "HorizontalCenterAlign", "StringField"),
            ("Band", "{@TxnRiskBand}", 110, None, "StringField")]
    global OUT
    prev, OUT = OUT, OUT.parent / "crystal"
    try:
        _NAME_TO_FILE.clear()
        build("Branch Transaction Summary - Prompt", "branch_transactions.xml",
              'SELECT\n  branches.br_name         AS "BRANCH_NAME",\n'
              '  transactions.txn_dt      AS "TXN_DATE",\n'
              '  transactions.acct_id     AS "ACCOUNT_ID",\n'
              '  members.first_nm         AS "FIRST_NAME",\n'
              '  members.last_nm          AS "LAST_NAME",\n'
              '  transactions.txn_type_cd AS "TXN_TYPE",\n'
              '  transactions.txn_amt     AS "AMOUNT"\n'
              'FROM cscu_core.transactions\n'
              'JOIN cscu_core.accounts ON accounts.acct_id = transactions.acct_id\n'
              'JOIN cscu_core.members  ON members.mbr_id  = accounts.mbr_id\n'
              'JOIN cscu_core.branches ON branches.br_id  = accounts.br_id\n'
              'ORDER BY branches.br_name, transactions.txn_dt',
              [("BRANCH_NAME","StringField"),("TXN_DATE","DateField"),("ACCOUNT_ID","StringField"),
               ("FIRST_NAME","StringField"),("LAST_NAME","StringField"),("TXN_TYPE","StringField"),
               ("AMOUNT","CurrencyField")],
              groups=["BRANCH_NAME"],
              params=[("Branch","StringField","Branch name","Phoenix Camelback")],
              record_selection="{BRANCHES.BR_NAME} = {?Branch} and {TRANSACTIONS.TXN_AMT} <> 0",
              formulas=[("FullName","StringField","{Command.FIRST_NAME} + ' ' + {Command.LAST_NAME}"),
                        ("RiskFlag","StringField",'If {Command.AMOUNT} > 10000 Then "REVIEW" Else "OK"'),
                        ("RunningBalance","NumberField",
                         "WhilePrintingRecords;\nShared NumberVar balance;\nbalance := balance + {Command.AMOUNT};\nbalance"),
                        ("TxnRiskBand","StringField",
                         'Select {Command.TXN_TYPE}\nCase "WIRE": "High risk"\nCase "ATM": "Low risk"\nDefault: "Standard"'),
                        # genuinely manual (local variable + assignment):
                        # keeps the ✨ AI-assist demo honest
                        ("AuditNote","StringField",
                         'Local StringVar note;\nnote := {Command.TXN_TYPE} + " flagged for " + {Command.FIRST_NAME};\nnote')],
              summaries=[("Sum of Command.AMOUNT","Sum","AMOUNT","BRANCH_NAME"),
                         ("Grand Total AMOUNT","Sum","AMOUNT",None)],
              areas=[masthead("Branch Transaction Summary", "Demo: working prompt - change the Branch parameter"),
                     column_header(cols), group_header("{Command.BRANCH_NAME}"), detail(cols),
                     totals_footer("GroupFooter","GF","Branch total:","{#Sum of Command.AMOUNT}"),
                     totals_footer("ReportFooter","RF","Grand total:","{#Grand Total AMOUNT}",size=10,big=True),
                     page_footer()])
    finally:
        OUT = prev


if __name__ == "__main__":
    for fn in (r1, r2, r3, r4, r5, r6):
        fn()
    flagship()
    for f in sorted(OUT.glob("0*.xml")):
        print("wrote", f.name)
    print("wrote ../crystal/branch_transactions.xml (flagship UI sample)")
