"""Generate the CSCU Crystal-migration ladder: nine RptToXml-shaped dumps of
increasing complexity, backed by the live cscu_core schema so each converts
AND renders end-to-end. Pages are A4 PORTRAIT (PAGE_W content width);
column sets are auto-fitted via fit(). Styled as polished, professional credit-union reports
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

# A4 PORTRAIT content width in points: 595pt page - 2 x 18pt margins.
# Every band anchors to this so the demos render print-ready in portrait.
PAGE_W = 559

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


def section(kind, name, height, objects, bg=None, suppress_condition=None):
    fill = _color_el("BackgroundColor", bg) if bg else ""
    cond = (f'<SectionAreaFormatConditionFormulas EnableSuppress={quoteattr(suppress_condition)}/>'
            if suppress_condition else "")
    fmt = f'<SectionFormat EnableSuppress="false">{cond}{fill}</SectionFormat>'
    return (f'<Area Kind="{kind}" Name="{name}Area"><Sections>'
            f'<Section Name="{name}" Height="{int(height*TW)}">{fmt}'
            f'<ReportObjects>{"".join(objects)}</ReportObjects></Section>'
            f'</Sections></Area>')


# ---- report skeleton ---------------------------------------------------------

_NAME_TO_FILE = {}


def build(name, filename, sql, fields, *, groups=None, formulas=None, params=None,
          summaries=None, record_selection=None, sorts=None, subreports=None, areas):
    """Emit one Report. filename=None returns the bare <Report> XML instead of
    writing a file - used to nest a report inside a parent's <SubReports>."""
    p = [f'<Report Name={quoteattr(name)} FileName={quoteattr(name + ".rpt")} HasSavedData="False">']
    if subreports:
        p.append("<SubReports>" + "".join(subreports) + "</SubReports>")
    fx = "".join(f'<Field Name="{c}" ValueType="{vt}"/>' for c, vt in fields)
    p.append('<Database><Tables>'
             '<Table Name="Command" Alias="Command" ClassName="CommandTable">'
             '<ConnectionInfo QE_DatabaseName="cscu_core" QE_DatabaseType="PostgreSQL" UserName="" Password=""/>'
             f'<Command>{escape(sql)}</Command><Fields>{fx}</Fields></Table></Tables></Database>')
    dd = ['<DataDefinition>']
    if record_selection:
        dd.append(f'<RecordSelectionFormula>{escape(record_selection)}</RecordSelectionFormula>')
    dd.append('<Groups>' + "".join(
        (f'<Group ConditionField="{{{g}}}"/>' if g.startswith("@")
         else f'<Group ConditionField="{{Command.{g}}}"/>')
        for g in (groups or [])) + '</Groups>')
    dd.append('<SortFields>' + "".join(
        f'<SortField Field={quoteattr(fld)} SortDirection="{d}" SortType="{st}"/>'
        for fld, d, st in (sorts or [])) + '</SortFields>')
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
    p.append('<PrintOptions PaperOrientation="Portrait" PaperSize="PaperA4">'
             '<PageMargins topMargin="360" leftMargin="360" bottomMargin="360" rightMargin="360"/></PrintOptions>')
    p.append(f'<ReportDefinition><Areas>{"".join(areas)}</Areas></ReportDefinition></Report>')
    xml = "".join(p)
    if filename:
        _NAME_TO_FILE[name] = filename
        (OUT / filename).write_text('<?xml version="1.0" encoding="utf-8"?>' + xml,
                                    encoding="utf-8")
    return xml


# ---- shared professional bands ----------------------------------------------

def masthead(title, subtitle):
    """Navy report-header band with logo, white title, gold subtitle + rule."""
    return section("ReportHeader", "RH", 58, [
        logo("Logo", 8, 6, 120, 44),
        text("Title", title, 150, 8, 300, 26, size=18, bold=True, color=WHITE),
        text("Sub", subtitle, 152, 34, PAGE_W - 160, 16, size=10, color=GOLD),
        text("Org", "Copperstate Credit Union", PAGE_W - 150, 10, 144, 16, size=9,
             color=WHITE, align="RightAlign"),
        box("GoldRule", 0, 55, PAGE_W, 2, GOLD),
    ], bg=NAVY)


def fit(cols, width=None):
    """Scale column widths proportionally so they fill exactly `width`
    (default: the portrait content width). Keeps every rung's column set
    print-ready without hand-tuning each layout."""
    width = width or PAGE_W
    total = sum(w for _, _, w, _, _ in cols)
    scaled, x = [], 0
    for i, (label, ref, w, align, vt) in enumerate(cols):
        w2 = width - x if i == len(cols) - 1 else round(w * width / total)
        scaled.append((label, ref, w2, align, vt))
        x += w2
    return scaled


def column_header(cols, reserve=0):
    """Dark column-label row with white bold labels and a bottom border."""
    labels, x = [], 0
    for label, _ref, w, align, _vt in fit(cols, PAGE_W - reserve):
        labels.append(text(f"h_{label}", label, x, 2, w, 18, size=9, bold=True,
                           color=WHITE, align=align, border=SLATE))
        x += w
    return section("PageHeader", "PH", 22, labels, bg=NAVY)


def detail(cols, extra=None, zebra=False, reserve=0):
    objs, x = [], 0
    for label, ref, w, align, vt in fit(cols, PAGE_W - reserve):
        objs.append(field(f"d_{label}", ref, x, 0, w, 15, size=9, align=align, color=INK))
        x += w
    objs.extend(extra or [])
    return section("Detail", "D", 17, objs)


def group_header(ref, extra=None):
    return section("GroupHeader", "GH", 22, [
        box("GhBar", 0, 0, PAGE_W, 20, LIGHT),
        field("GroupVal", ref, 6, 2, 400, 17, size=11, bold=True, color=NAVY),
        *(extra or []),
    ])


def totals_footer(kind, name, label, ref, size=9, big=False):
    return section(kind, name, 22, [
        box("TotRule", PAGE_W - 306, 0, 306, 1, GOLD),
        text(f"{name}Lbl", label, PAGE_W - 306, 3, 150, 16, size=size, bold=True, color=NAVY),
        field(f"{name}Val", ref, PAGE_W - 146, 3, 130, 16, size=size, bold=True,
              color=(GOLD if big else NAVY), align="RightAlign"),
    ])


def page_footer():
    return section("PageFooter", "PF", 22, [
        box("PfRule", 0, 0, PAGE_W, 1, SLATE),
        field("PrintDate", "PrintDate", 0, 4, 140, 14, size=8, color=SLATE),
        field("PageNum", "PageNumber", PAGE_W - 106, 4, 100, 14, size=8, color=SLATE, align="RightAlign"),
        text("Conf", "Confidential — Copperstate Credit Union", 145, 4, PAGE_W - 300, 14,
             size=8, color=SLATE, align="HorizontalCenterAlign"),
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
                     box("RfRule", PAGE_W - 306, 0, 306, 1, GOLD),
                     text("GtLbl", "Grand total:", PAGE_W - 306, 3, 150, 16, size=10, bold=True, color=NAVY),
                     field("GtVal", "{#Grand Total BAL_AMT}", PAGE_W - 146, 3, 130, 16, size=10,
                           bold=True, color=GOLD, align="RightAlign"),
                     chart("BalChart", 20, 26, PAGE_W - 40, 230, "Bar",
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
    extra = [field("Flow", "{@FlowType}", PAGE_W - 50, 0, 50, 15, size=9,
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
                 column_header(cols, reserve=52), group_header("{Command.BR_NAME}"),
                 detail(cols, extra, reserve=52),
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
        box("M1", 0, 0, PAGE_W, 24, NAVY),
        field("MemberHdr", "{@FullName}", 8, 3, 300, 18, size=12, bold=True, color=WHITE),
        field("MemberNo", "{Command.MBR_NO}", PAGE_W - 206, 4, 200, 16, size=9, color=GOLD, align="RightAlign")])
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
    # detail with a conditional font-color on the balance (delinquent = red);
    # built from the SAME fitted columns the header row uses
    det = []
    x = 0
    for lbl, ref, w, al, vt in fit(cols):
        if lbl == "Balance":
            det.append('<FieldObject Name="d_Balance" DataSource="{Command.PRIN_BAL_AMT}" '
                       f'Left="{x*TW}" Top="0" Width="{w*TW}" Height="{15*TW}" HorizontalAlignment="RightAlign">'
                       '<Font FontName="Arial" Size="9"/>'
                       '<FontColorConditionFormulas Color="If {Command.LN_STATUS} = \'Delinquent30\' Then crRed Else crBlack"/>'
                       '</FieldObject>')
        else:
            det.append(field(f"d_{lbl}", ref, x, 0, w, 15, size=9, align=al, color=INK))
        x += w
    gf = section("GroupFooter", "GF", 40, [
        box("Rule", PAGE_W - 506, 0, 506, 1, GOLD),
        text("SumLbl", "Portfolio balance:", PAGE_W - 506, 3, 150, 14, size=8, bold=True, color=NAVY),
        field("SumBal", "{#Sum of PRIN_BAL_AMT}", PAGE_W - 346, 3, 130, 14, size=8, bold=True, color=NAVY, align="RightAlign"),
        text("AvgLbl", "Avg APR:", PAGE_W - 506, 20, 150, 14, size=8, color=SLATE),
        field("AvgApr", "{#Average of APR_RT}", PAGE_W - 346, 20, 130, 14, size=8, color=SLATE, align="RightAlign"),
        text("SdLbl", "APR std dev:", PAGE_W - 196, 20, 100, 14, size=8, color=SLATE),
        field("SdApr", "{#StdDev of APR_RT}", PAGE_W - 91, 20, 90, 14, size=8, color=SLATE, align="RightAlign")])
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
                 # suppress paid-off loans - becomes a band visible-expression
                 section("Detail", "D", 17, det,
                         suppress_condition="{Command.PRIN_BAL_AMT} = 0"),
                 gf, page_footer()])


def r6():
    cols = [("Filed", "{Command.FILED_DT}", 110, None, "DateField"),
            ("Member", "{@FullName}", 170, None, "StringField"),
            ("Activity", "{Command.ACTIVITY_TYPE_CD}", 150, None, "StringField"),
            ("Amount", "{Command.SAR_AMT}", 120, "RightAlign", "CurrencyField"),
            ("Status", "{Command.SAR_STATUS}", 120, None, "StringField")]
    # linked subreport: the member's KYC history, filtered by the parent row's
    # MBR_ID through Crystal's Pm-<field> linked-parameter convention
    kyc = build("sar_kyc", None,
                'SELECT k.mbr_id AS "MBR_ID", k.review_dt AS "REVIEW_DT",\n'
                '       k.risk_rating_cd AS "RISK_RATING_CD", k.kyc_status AS "KYC_STATUS"\n'
                'FROM cscu_core.kyc_reviews k',
                [("MBR_ID","NumberField"),("REVIEW_DT","DateField"),
                 ("RISK_RATING_CD","StringField"),("KYC_STATUS","StringField")],
                params=[("Pm-Command.MBR_ID","NumberField","","")],
                record_selection="{Command.MBR_ID} = {?Pm-Command.MBR_ID}",
                areas=[section("ReportHeader", "KH", 14, [
                           text("KycLbl", "KYC review history", 20, 0, 200, 12,
                                size=8, bold=True, color=SLATE)]),
                       section("Detail", "KD", 13, [
                           field("k_dt", "{Command.REVIEW_DT}", 20, 0, 110, 12, size=8, color=INK),
                           field("k_risk", "{Command.RISK_RATING_CD}", 140, 0, 120, 12, size=8, color=INK),
                           field("k_status", "{Command.KYC_STATUS}", 270, 0, 140, 12, size=8, color=INK)])])
    extra = ['<SubreportObject Name="KycSub" SubreportName="sar_kyc" '
             f'Left="0" Top="{17*TW}" Width="{500*TW}" Height="{30*TW}"/>']
    rf = section("ReportFooter", "RF", 60, [
        box("PivotBar", 0, 0, PAGE_W, 1, GOLD),
        '<CrossTabObject Name="ActivityPivot" Left="0" Top="200" Width="8060" Height="1000"/>',
        text("Note", "Activity type x status pivot (rebuild as PRD crosstab)", 0, 4, 500, 14,
             size=8, color=SLATE)])
    build("Suspicious Activity - Subreport & Cross-tab", "06_suspicious_activity.xml",
          'SELECT s.mbr_id AS "MBR_ID", s.filed_dt AS "FILED_DT", m.first_nm AS "FIRST_NM",\n'
          '       m.last_nm AS "LAST_NM", s.activity_type_cd AS "ACTIVITY_TYPE_CD",\n'
          '       s.sar_amt AS "SAR_AMT", s.sar_status AS "SAR_STATUS", s.narrative_txt AS "NARRATIVE_TXT"\n'
          'FROM cscu_core.suspicious_activity s JOIN cscu_core.members m ON m.mbr_id = s.mbr_id\n'
          'ORDER BY s.filed_dt',
          [("MBR_ID","NumberField"),("FILED_DT","DateField"),("FIRST_NM","StringField"),
           ("LAST_NM","StringField"),("ACTIVITY_TYPE_CD","StringField"),("SAR_AMT","CurrencyField"),
           ("SAR_STATUS","StringField"),("NARRATIVE_TXT","StringField")],
          formulas=[("FullName","StringField","{Command.FIRST_NM} + ' ' + {Command.LAST_NM}")],
          subreports=[kyc],
          areas=[masthead("Suspicious Activity Report (SAR)", "Demo: linked subreport and cross-tab TODO"),
                 column_header(cols), detail(cols, extra), rf, page_footer()])


def r7():
    """Rung 7 - every v1.19-1.21 translator upgrade in one report: Select Case
    (multi-value), an in-range test, an inlined local-variable alias, and
    sort directions consumed from the Crystal SortField list."""
    cols = [("Card #", "{Command.CARD_NO}", 150, None, "StringField"),
            ("Holder", "{@Holder}", 170, None, "StringField"),
            ("Issued", "{Command.ISSUED_DT}", 100, None, "DateField"),
            ("Expires", "{Command.EXP_DT}", 100, None, "DateField"),
            ("Window", "{@ExpiryWindow}", 106, None, "StringField"),
            ("Status", "{Command.CARD_STATUS}", 90, None, "StringField"),
            ("Action", "{@CardAction}", 90, None, "StringField")]
    build("Card Program Review - Select Case, Ranges & Sorts", "07_card_program.xml",
          'SELECT c.card_no AS "CARD_NO", m.first_nm AS "FIRST_NM", m.last_nm AS "LAST_NM",\n'
          '       c.card_type_cd AS "CARD_TYPE_CD", c.card_status AS "CARD_STATUS",\n'
          '       c.issued_dt AS "ISSUED_DT", c.exp_dt AS "EXP_DT"\n'
          'FROM cscu_core.cards c\n'
          'JOIN cscu_core.accounts a ON a.acct_id = c.acct_id\n'
          'JOIN cscu_core.members  m ON m.mbr_id = a.mbr_id\n'
          'ORDER BY c.card_type_cd DESC, c.issued_dt DESC',
          [("CARD_NO","StringField"),("FIRST_NM","StringField"),("LAST_NM","StringField"),
           ("CARD_TYPE_CD","StringField"),("CARD_STATUS","StringField"),
           ("ISSUED_DT","DateField"),("EXP_DT","DateField")],
          groups=["CARD_TYPE_CD"],
          sorts=[("{Command.CARD_TYPE_CD}", "DescendingOrder", "GroupSortField"),
                 ("{Command.ISSUED_DT}", "DescendingOrder", "RecordSortField")],
          formulas=[
              # Select Case with a multi-value branch -> nested IF + OR
              ("CardAction","StringField",
               'Select {Command.CARD_STATUS}\nCase "Blocked", "Expired": "Action required"\n'
               'Case "Active": "OK"\nDefault: "Review"'),
              # in-range test -> AND(>= ; <=)
              ("ExpiryWindow","StringField",
               'If Year({Command.EXP_DT}) in 2026 to 2027 Then "Expiring soon" Else "Current"'),
              # single-assignment local variable -> inlined deterministically
              ("Holder","StringField",
               'Local StringVar h;\nh := {Command.FIRST_NM} + \' \' + {Command.LAST_NM};\nh')],
          areas=[masthead("Card Program Review", "Demo: Select Case, ranges, alias inlining and sort directions"),
                 column_header(cols), group_header("{Command.CARD_TYPE_CD}"),
                 detail(cols), page_footer()])


def r8():
    """Rung 8 - the STRESS LAB: deliberately stacks complexity to map the
    converter's boundaries. Three nested groups (one on a FORMULA - a known
    boundary for generated ORDER BY), a linked subreport in a group footer
    whose child has its own group + summary + conditional formatting, a
    second subreport with TWO link fields, an unlinked subreport in the
    PAGE footer (PRD forbids subreports in page bands - boundary), the full
    formula zoo, and a multi-value prompt."""
    # child 1: member KYC history WITH its own group + summary + cond. format
    kyc = build("stress_kyc", None,
                'SELECT k.mbr_id AS "MBR_ID", k.review_dt AS "REVIEW_DT",\n'
                '       k.risk_rating_cd AS "RISK_RATING_CD", k.kyc_status AS "KYC_STATUS"\n'
                'FROM cscu_core.kyc_reviews k',
                [("MBR_ID","NumberField"),("REVIEW_DT","DateField"),
                 ("RISK_RATING_CD","StringField"),("KYC_STATUS","StringField")],
                groups=["RISK_RATING_CD"],
                summaries=[("Count of KYC_ID","Count","MBR_ID","RISK_RATING_CD")],
                formulas=[("RiskTag","StringField",
                           'Select {Command.RISK_RATING_CD} Case "HIGH": "!" Default: ""')],
                params=[("Pm-Command.MBR_ID","NumberField","","")],
                record_selection="{Command.MBR_ID} = {?Pm-Command.MBR_ID}",
                areas=[section("GroupHeader", "KGH", 13, [
                           field("kg", "{Command.RISK_RATING_CD}", 20, 0, 150, 12, size=8, bold=True, color=SLATE)]),
                       section("Detail", "KD", 12, [
                           field("kd1", "{Command.REVIEW_DT}", 40, 0, 100, 11, size=8, color=INK),
                           field("kd2", "{Command.KYC_STATUS}", 150, 0, 120, 11, size=8, color=INK),
                           field("kd3", "{@RiskTag}", 280, 0, 20, 11, size=8, color=INK)])])
    # child 2: transactions for the member AT a branch - TWO link fields
    txns = build("stress_txns", None,
                 'SELECT a.mbr_id AS "MBR_ID", a.br_id AS "BR_ID", t.txn_dt AS "TXN_DT",\n'
                 '       t.txn_amt AS "TXN_AMT"\n'
                 'FROM cscu_core.transactions t JOIN cscu_core.accounts a ON a.acct_id = t.acct_id',
                 [("MBR_ID","NumberField"),("BR_ID","NumberField"),
                  ("TXN_DT","DateField"),("TXN_AMT","CurrencyField")],
                 params=[("Pm-Command.MBR_ID","NumberField","",""),
                         ("Pm-Command.BR_ID","NumberField","","")],
                 record_selection="{Command.MBR_ID} = {?Pm-Command.MBR_ID} and {Command.BR_ID} = {?Pm-Command.BR_ID}",
                 areas=[section("Detail", "TD", 12, [
                            field("td1", "{Command.TXN_DT}", 40, 0, 100, 11, size=8, color=INK),
                            field("td2", "{Command.TXN_AMT}", 150, 0, 110, 11, size=8,
                                  align="RightAlign", color=INK)])])
    # child 3: unlinked branch directory - goes in the PAGE footer (boundary)
    branches = build("stress_branches", None,
                     'SELECT b.br_name AS "BR_NAME" FROM cscu_core.branches b',
                     [("BR_NAME","StringField")],
                     areas=[section("Detail", "BD", 11, [
                                field("bd1", "{Command.BR_NAME}", 0, 0, 200, 10, size=7, color=SLATE)])])
    cols = [("Date", "{Command.TXN_DT}", 100, None, "DateField"),
            ("Member", "{@FullName}", 160, None, "StringField"),
            ("Type", "{Command.TXN_TYPE_CD}", 90, None, "StringField"),
            ("Amount", "{Command.TXN_AMT}", 110, "RightAlign", "CurrencyField"),
            ("Tier", "{@Tier}", 110, None, "StringField"),
            ("Flag", "{@BigTxn}", 80, None, "StringField"),
            ("Bal", "{@RunBal}", 110, "RightAlign", "NumberField")]
    gf2 = section("GroupFooter", "SGF2", 56, [
        text("KycHdr", "Member due diligence:", 20, 2, 200, 12, size=8, bold=True, color=NAVY),
        f'<SubreportObject Name="KycSub" SubreportName="stress_kyc" Left="{20*TW}" Top="{14*TW}" Width="{(PAGE_W - 40)*TW}" Height="{18*TW}"/>',
        f'<SubreportObject Name="TxnSub" SubreportName="stress_txns" Left="{20*TW}" Top="{36*TW}" Width="{(PAGE_W - 40)*TW}" Height="{18*TW}"/>'])
    pf = section("PageFooter", "SPF", 30, [
        text("pfl", "Branch directory:", 0, 2, 120, 10, size=7, color=SLATE),
        f'<SubreportObject Name="BranchSub" SubreportName="stress_branches" Left="{130*TW}" Top="0" Width="{300*TW}" Height="{28*TW}"/>'])
    build("Stress Lab - Boundaries", "08_stress_lab.xml",
          'SELECT b.br_name AS "BR_NAME", m.mbr_id AS "MBR_ID", a.br_id AS "BR_ID",\n'
          '       m.mbr_no AS "MBR_NO", m.first_nm AS "FIRST_NM", m.last_nm AS "LAST_NM",\n'
          '       t.txn_dt AS "TXN_DT", t.txn_type_cd AS "TXN_TYPE_CD", t.txn_amt AS "TXN_AMT"\n'
          'FROM cscu_core.transactions t\n'
          'JOIN cscu_core.accounts a ON a.acct_id = t.acct_id\n'
          'JOIN cscu_core.members  m ON m.mbr_id = a.mbr_id\n'
          'JOIN cscu_core.branches b ON b.br_id = a.br_id\n'
          'ORDER BY b.br_name, m.mbr_no, t.txn_dt',
          [("BR_NAME","StringField"),("MBR_ID","NumberField"),("BR_ID","NumberField"),
           ("MBR_NO","StringField"),("FIRST_NM","StringField"),("LAST_NM","StringField"),
           ("TXN_DT","DateField"),("TXN_TYPE_CD","StringField"),("TXN_AMT","CurrencyField")],
          groups=["BR_NAME", "MBR_NO", "@Tier"],   # group ON A FORMULA = boundary
          params=[("TxnType","StringField","Transaction type","POS")],
          record_selection="{Command.TXN_TYPE_CD} = {?TxnType}",
          summaries=[("Sum of TXN_AMT","Sum","TXN_AMT","MBR_NO"),
                     ("Grand Total TXN_AMT","Sum","TXN_AMT",None),
                     ("StdDev of TXN_AMT","StdDeviation","TXN_AMT","BR_NAME")],
          formulas=[("FullName","StringField","{Command.FIRST_NM} + ' ' + {Command.LAST_NM}"),
                    ("Tier","StringField",
                     'Select {Command.TXN_AMT}\nCase 0 To 500: "Retail"\nCase Is > 5000: "Large"\nDefault: "Mid"'),
                    ("BigTxn","StringField",
                     'If {Command.TXN_AMT} in 5000 to 20000 Then "check" Else ""'),
                    ("RunBal","NumberField",
                     "WhilePrintingRecords;\nShared NumberVar rb;\nrb := rb + {Command.TXN_AMT};\nrb"),
                    ("Impossible","StringField",
                     'Local StringVar a;\nLocal StringVar b;\nb := "x";\na := {Command.TXN_TYPE_CD} + b;\na')],
          subreports=[kyc, txns, branches],
          areas=[masthead("Stress Lab", "Demo: boundary hunting - nested groups, multi-link subreports, page-band subreport"),
                 column_header(cols),
                 section("GroupHeader", "SGH1", 20, [
                     box("g1bar", 0, 0, PAGE_W, 18, LIGHT),
                     field("g1", "{Command.BR_NAME}", 6, 2, 400, 15, size=10, bold=True, color=NAVY)]),
                 section("GroupHeader", "SGH2", 16, [
                     field("g2", "{@FullName}", 20, 1, 300, 14, size=9, bold=True, color=SLATE)]),
                 section("GroupHeader", "SGH3", 13, [
                     field("g3", "{@Tier}", 40, 0, 200, 12, size=8, color=GOLD)]),
                 detail(cols), gf2,
                 totals_footer("ReportFooter", "SRF", "Grand total:", "{#Grand Total TXN_AMT}", big=True),
                 pf])


def r9():
    """Rung 9 - a cross-tab that CONVERTS: the CrossTabObject carries the
    <CrossTabDefinition> block (rows/columns/summaries), which is exactly what
    a consultant hand-adds to a real dump (the free SAP SDK cannot export it).
    Converts to a live PRD crosstab: branches x transaction types, summed."""
    build("Branch Activity Matrix - Cross-tab", "09_branch_activity_matrix.xml",
          'SELECT b.br_name AS "BR_NAME", t.txn_type_cd AS "TXN_TYPE",\n'
          '       t.txn_amt AS "TXN_AMT"\n'
          'FROM cscu_core.transactions t\n'
          'JOIN cscu_core.accounts a ON a.acct_id = t.acct_id\n'
          'JOIN cscu_core.branches b ON b.br_id = a.br_id',
          [("BR_NAME", "StringField"), ("TXN_TYPE", "StringField"),
           ("TXN_AMT", "CurrencyField")],
          areas=[masthead("Branch Activity Matrix",
                          "Demo: cross-tab converted to a live PRD crosstab"),
                 section("ReportHeader", "RH2", 240, [
                     text("XtLbl", "Transaction amounts by branch and type",
                          0, 4, 400, 14, size=9, bold=True, color=SLATE),
                     '<CrossTabObject Name="ActivityMatrix" Left="0" Top="440" '
                     f'Width="{520*TW}" Height="{200*TW}">'
                     '<CrossTabDefinition>'
                     '<RowFields><Field FieldName="{Command.BR_NAME}"/></RowFields>'
                     '<ColumnFields><Field FieldName="{Command.TXN_TYPE}"/></ColumnFields>'
                     '<SummaryFields><Field FieldName="{Command.TXN_AMT}" Operation="Sum"/></SummaryFields>'
                     '</CrossTabDefinition></CrossTabObject>',
                 ]),
                 page_footer()])


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
                        # genuinely manual (TWO local variables - real state,
                        # not an inlinable alias): keeps the ✨ AI-assist demo honest
                        ("AuditNote","StringField",
                         'Local StringVar note;\nLocal StringVar sep;\nsep := " / ";\n'
                         'note := {Command.TXN_TYPE} + sep + {Command.FIRST_NAME};\nnote')],
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
    for fn in (r1, r2, r3, r4, r5, r6, r7, r8, r9):
        fn()
    flagship()
    for f in sorted(OUT.glob("0*.xml")):
        print("wrote", f.name)
    print("wrote ../crystal/branch_transactions.xml (flagship UI sample)")
