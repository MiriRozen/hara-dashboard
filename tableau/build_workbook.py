"""
Generates tableau/hara-runs.twb from the CSVs in tableau/data.

The workbook is code, not clicks: every sheet, colour, filter and action below is
reviewable in a diff and reproducible after the data changes.
    python prep/hara_prep.py && python tableau/build_workbook.py
"""
from __future__ import annotations

import csv
from pathlib import Path
import os
import re
import uuid
from xml.sax.saxutils import escape, quoteattr

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

INT_COLS = {
    "row_order", "col_pos", "bar_order", "order_index", "sort_rank", "needs_attention", "attention_count",
    "value_micro", "initial_micro", "approved_micro", "spent_micro", "unresolved_micro",
    "extension_micro", "remaining_micro", "pct_of_approved", "pct_of_initial", "cost_is_complete", "open_reservation_micro",
    "is_extended", "is_overrun", "is_downgraded", "is_running", "downgrade_count", "cost_gap_micro",
    "duration_sec", "agent_count", "cost_micro", "node_order",
}
DISCRETE_INTS = {"row_order", "col_pos", "bar_order", "order_index", "node_order"}

FONT = "Arial"  # web-safe on Tableau Public and has Hebrew glyphs
INK, MUTED, LINE = "#1b1f24", "#5b6470", "#dde1e6"
TONES = {
    "critical": "#b42318",
    "warning": "#9a5b00",
    "ok": "#1d6b3f",
    "neutral": "#1f5fa8",
    "plain": INK,
    "muted": MUTED,
}
BAR_KINDS = {"initial": "#c9ced6", "ceiling": "#8a93a0", "spent": "#2f6fb5", "over": "#b42318", "unknown": "#e7a0a0"}

DEFAULT_RUN = "run-2c91e7"
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "prep"))
from tableau_views import rtl_lines as rtl  # noqa: E402  (same RTL embedding as the data)
CELL_SCALE = 1.04  # Tableau cell-w units vs dashboard pixels (measured)
CAPTIONS = {"status_he": "מצב הריצה", "tone_he": "דרגת תשומת לב"}
COLOR_FIELDS = {"tone", "kind", "status_he", "reasons_tone"}
DATASOURCES = ["cells", "summary", "run_header", "budget_bars", "nodes"]
# absolute while developing (.twb), relative inside the packaged .twbx
PATHS = {"csv_dir": DATA.as_posix(), "hyper_dir": (HERE / "extracts").as_posix()}
SHEET_NAME = re.compile(r"<worksheet name=(['\"])(.*?)\1")


def simple_id(name: str) -> str:
    return f"<simple-id uuid='{{{str(uuid.uuid5(uuid.NAMESPACE_URL, 'hara/' + name)).upper()}}}' />"


def q(s: str) -> str:
    return quoteattr(s)


# ---------------------------------------------------------------- data sources


def read_header(name: str) -> list[str]:
    with (DATA / f"{name}.csv").open(encoding="utf-8") as f:
        return next(csv.reader(f))


def ds_name(name: str) -> str:
    return f"federated.{name}"


def datasource(name: str, calcs: dict[str, tuple[str, str, str]] | None = None, style: str = "") -> str:
    cols = read_header(name)
    conn = f"textscan.{name}"
    obj = f"{name}.csv_" + uuid.uuid5(uuid.NAMESPACE_URL, "hara/ds/" + name).hex.upper()
    col_xml = "\n".join(
        f"            <column datatype='{'integer' if c in INT_COLS else 'string'}' name={q(c)} ordinal='{i}' />"
        for i, c in enumerate(cols)
    )
    relation = f"""<relation connection='{conn}' name='{name}.csv' table='[{name}#csv]' type='table'>
          <columns character-set='UTF-8' header='yes' locale='he_IL' separator=','>
{col_xml}
          </columns>
        </relation>"""
    captions = "\n".join(
        f"      <column caption={q(CAPTIONS[c])} datatype='string' name='[{c}]' role='dimension' type='nominal' />"
        for c in cols if c in CAPTIONS
    ) + "".join(
        f"\n      <column datatype='string' name='[{c}]' role='dimension' type='nominal' />"
        for c in cols if c in COLOR_FIELDS and c not in CAPTIONS
    )
    # the palette in `style` binds to these instances, not to the raw columns; instances follow all columns
    instances = "\n".join(
        f"      <column-instance column='[{c}]' derivation='None' name='[none:{c}:nk]' pivot='key' type='nominal' />"
        for c in cols if c in COLOR_FIELDS
    )
    field_meta = captions + "\n" + "\n".join(
        f"      <column datatype='integer' name='[{c}]' role='dimension' type='ordinal' />"
        for c in cols if c in DISCRETE_INTS
    )
    calc_xml = "\n".join(
        f"""      <column caption={q(cap)} datatype='{dt}' name='[{cid}]' role='{"measure" if dt in ("real", "integer") else "dimension"}' type='{"quantitative" if dt in ("real", "integer") else "nominal"}'>
        <calculation class='tableau' formula={q(formula)} />
      </column>"""
        for cid, (cap, dt, formula) in (calcs or {}).items()
    )
    return f"""    <datasource caption='{name}' inline='true' name='{ds_name(name)}' version='18.1'>
      <connection class='federated'>
        <named-connections>
          <named-connection caption='{name}' name='{conn}'>
            <connection class='textscan' directory={q(PATHS["csv_dir"])} filename='{name}.csv' password='' server='' />
          </named-connection>
        </named-connections>
        {relation}
      </connection>
      <aliases enabled='yes' />
      <column caption='{name}.csv' datatype='table' name='[__tableau_internal_object_id__].[{obj}]' role='measure' type='quantitative' />
{field_meta}
{calc_xml}
{instances}
      <extract count='-1' enabled='true' object-id='' units='records' user-specific='false'>
        <connection access_mode='readonly' author-locale='en_US' class='hyper' dbname={q(PATHS["hyper_dir"] + "/" + name + ".hyper")} default-settings='hyper' schema='Extract' sslmode='' tablename='Extract' update-time='09/27/2026 12:00:00 PM' username='tableau_internal_user'>
          <relation name='Extract' table='[Extract].[Extract]' type='table' />
        </connection>
      </extract>
      <layout dim-ordering='alphabetic' measure-ordering='alphabetic' show-structure='true' />
{style}
      <object-graph>
        <objects>
          <object caption='{name}.csv' id='{obj}'>
            <properties context=''>
              {relation}
            </properties>
            <properties context='extract'>
              <relation name='Extract' table='[Extract].[Extract]' type='table' />
            </properties>
          </object>
        </objects>
      </object-graph>
    </datasource>"""


def write_extract(name: str, out_dir: Path) -> None:
    """One .hyper per CSV — Tableau Public only accepts extracted data. Types match the CSV schema."""
    from tableauhyperapi import (Connection, CreateMode, HyperProcess, Inserter, SqlType, TableDefinition,
                                 TableName, Telemetry)

    with (DATA / f"{name}.csv").open(encoding="utf-8") as f:
        rows = list(csv.reader(f))
    header, body = rows[0], rows[1:]
    table = TableDefinition(TableName("Extract", "Extract"), [
        TableDefinition.Column(c, SqlType.big_int() if c in INT_COLS else SqlType.text()) for c in header
    ])
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{name}.hyper"
    with HyperProcess(Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hyper:
        with Connection(hyper.endpoint, target, CreateMode.CREATE_AND_REPLACE) as conn:
            conn.catalog.create_schema("Extract")
            conn.catalog.create_table(table)
            with Inserter(conn, table) as ins:
                for r in body:
                    ins.add_row([
                        (int(v) if v != "" else None) if c in INT_COLS else v for c, v in zip(header, r)
                    ])
                ins.execute()


def palette_style(*pairs: tuple[str, dict[str, str]]) -> str:
    """One <style> with a fixed colour map per field (field, {value: colour})."""
    enc = []
    for field, mapping in pairs:
        maps = "\n".join(
            f"            <map to='{color}'>\n              <bucket>&quot;{key}&quot;</bucket>\n            </map>"
            for key, color in mapping.items()
        )
        enc.append(f"""          <encoding attr='color' field='[none:{field}:nk]' type='palette'>
{maps}
          </encoding>""")
    return f"""      <style>
        <style-rule element='mark'>
{chr(10).join(enc)}
        </style-rule>
      </style>"""


def short(title: str, limit: int = 60) -> str:
    """Selector labels: keep the start of a long title (the words that identify the run)."""
    return title if len(title) <= limit else title[: limit - 1].rstrip() + "…"


def parameters_ds(runs: list[dict]) -> str:
    members = "\n".join(
        f"        <member alias={q(rtl(short(r['title'])))} value={q(chr(34) + r['run_id'] + chr(34))} />" for r in runs
    )
    return f"""    <datasource hasconnection='false' inline='true' name='Parameters' version='18.1'>
      <aliases enabled='yes' />
      <column caption='ריצה' datatype='string' name='[pRun]' param-domain-type='list' role='measure' type='nominal' value='&quot;{DEFAULT_RUN}&quot;'>
        <calculation class='tableau' formula='&quot;{DEFAULT_RUN}&quot;' />
        <members>
{members}
        </members>
      </column>
    </datasource>"""


SELECTED = ("נבחרה", "boolean", "[run_id] = [Parameters].[pRun]")
CALCS = {"is_selected": SELECTED}

# ---------------------------------------------------------------- worksheets


def inst(ds: str, field: str, kind: str = "nk") -> str:
    """Column-instance reference, e.g. [federated.cells].[none:text:nk]."""
    return f"[{ds_name(ds)}].[none:{field}:{kind}]"


def deps(ds: str, fields: list[tuple[str, str, str]]) -> str:
    """fields: (name, datatype, kind) — kind nk (nominal), ok (ordinal), qk (quantitative sum)."""
    out = [f"          <datasource-dependencies datasource='{ds_name(ds)}'>"]
    for name, dt, kind in fields:
        role = "measure" if kind == "qk" else "dimension"
        typ = {"nk": "nominal", "ok": "ordinal", "qk": "quantitative"}[kind]
        if name in CALCS:
            cap, cdt, formula = CALCS[name]
            out.append(
                f"            <column caption={q(cap)} datatype='{cdt}' name='[{name}]' role='dimension' type='nominal'>\n"
                f"              <calculation class='tableau' formula={q(formula)} />\n            </column>"
            )
        else:
            out.append(f"            <column datatype='{dt}' name='[{name}]' role='{role}' type='{typ}' />")
        deriv = "Sum" if kind == "qk" else "None"
        prefix = "sum" if kind == "qk" else "none"
        out.append(
            f"            <column-instance column='[{name}]' derivation='{deriv}' name='[{prefix}:{name}:{kind}]' pivot='key' type='{typ}' />"
        )
    out.append("          </datasource-dependencies>")
    return "\n".join(out)


def member_filter(ds: str, field: str, value: str, kind: str = "nk", quoted: bool = True) -> str:
    member = f"&quot;{value}&quot;" if quoted else value
    return f"""          <filter class='categorical' column='{inst(ds, field, kind)}'>
            <groupfilter function='member' level='[none:{field}:{kind}]' member='{member}' user:ui-domain='database' user:ui-enumeration='inclusive' user:ui-marker='enumerate' />
          </filter>"""


def title_xml(text: str) -> str:
    return f"""      <layout-options>
        <title>
          <formatted-text>
            <run bold='true' fontname='{FONT}' fontsize='12' fontcolor='{INK}'>{escape(rtl(text))}</run>
          </formatted-text>
        </title>
      </layout-options>"""


def cells_sheet(name: str, table: str, *, by_param: bool, title: str, cell_w: int, cell_h: int,
                header_size: int = 10, cell_size: int = 10) -> str:
    """A table drawn from the long `cells` table. Tableau gives every column of one field the same
    width, so tables are designed with columns of similar weight. Helper headers are hidden."""
    ds = "cells"
    fields = [("table", "string", "nk"), ("row_order", "integer", "ok"), ("col_pos", "integer", "ok"),
              ("col_header", "string", "nk"), ("text", "string", "nk"), ("tone", "string", "nk"),
              ("run_id", "string", "nk")]
    filters = [member_filter(ds, "table", table)]
    slices = [inst(ds, "table")]
    if by_param:
        fields.append(("is_selected", "boolean", "nk"))
        filters.append(member_filter(ds, "is_selected", "true", quoted=False))
        slices.append(inst(ds, "is_selected"))
    else:
        # user-facing quick filters (shown on the dashboard); start with everything selected
        for f in ("status_he", "tone_he"):
            fields.append((f, "string", "nk"))
            filters.append(
                f"""          <filter class='categorical' column='{inst(ds, f)}'>
            <groupfilter function='level-members' level='[none:{f}:nk]' user:ui-enumeration='all' user:ui-marker='enumerate' />
          </filter>"""
            )
            slices.append(inst(ds, f))
    slices_xml = "\n".join(f"            <column>{s}</column>" for s in slices)
    return f"""    <worksheet name={q(name)}>
{title_xml(title)}
      <table>
        <view>
          <datasources>
            <datasource caption='cells' name='{ds_name(ds)}' />
          </datasources>
{deps(ds, fields)}
{chr(10).join(filters)}
          <slices>
{slices_xml}
          </slices>
          <aggregation value='true' />
        </view>
        <style>
          <style-rule element='cell'>
            <format attr='text-align' value='right' />
            <format attr='vertical-align' value='top' />
            <format attr='font-family' value='{FONT}' />
            <format attr='font-size' value='{cell_size}' />
            <format attr='cell-w' value='{cell_w}' />
            <format attr='cell-h' value='{cell_h}' />
            <format attr='cell' value='20' />
            <format attr='cell-q' value='100' />
          </style-rule>
          <style-rule element='header'>
            <format attr='text-align' value='right' />
            <format attr='font-family' value='{FONT}' />
            <format attr='font-size' value='{header_size}' />
            <format attr='font-weight' value='bold' />
            <format attr='color' value='{MUTED}' />
          </style-rule>
          <style-rule element='label'>
            <format attr='display' field='{inst(ds, "col_pos", "ok")}' value='false' />
            <format attr='display' field='{inst(ds, "row_order", "ok")}' value='false' />
          </style-rule>
          <style-rule element='worksheet'>
            <format attr='font-family' value='{FONT}' />
            <format attr='display-field-labels' scope='rows' value='false' />
            <format attr='display-field-labels' scope='cols' value='false' />
          </style-rule>
        </style>
        <panes>
          <pane selection-relaxation-option='selection-relaxation-allow'>
            <view>
              <breakdown value='auto' />
            </view>
            <mark class='Text' />
            <encodings>
              <text column='{inst(ds, "text")}' />
              <color column='{inst(ds, "tone")}' />
              <lod column='{inst(ds, "run_id")}' />
            </encodings>
            {tooltip([(inst(ds, "col_header"), True), (inst(ds, "text"), False)] + ([("=לחיצה פותחת את פרטי הריצה", False)] if not by_param else []))}
            <style>
              <style-rule element='mark'>
                <format attr='mark-labels-show' value='true' />
                <format attr='text-align' value='right' />
              </style-rule>
            </style>
          </pane>
        </panes>
        <rows>{inst(ds, "row_order", "ok")}</rows>
        <cols>({inst(ds, "col_pos", "ok")} / {inst(ds, "col_header")})</cols>
      </table>
      {simple_id(name)}
    </worksheet>"""


def tooltip(parts: list[tuple[str, bool]]) -> str:
    """Hebrew tooltip instead of Tableau's raw field dump. parts: (field ref or '=literal', bold)."""
    runs = []
    for i, (ref, bold) in enumerate(parts):
        body = escape(rtl(ref[1:])) if ref.startswith("=") else f"&lt;{ref}&gt;"
        b = " bold='true'" if bold else ""
        color = MUTED if ref.startswith("=") else INK
        runs.append(f"<run{b} fontcolor='{color}' fontname='{FONT}' fontsize='10'>{body}</run>")
        if i < len(parts) - 1:
            runs.append("<run>Æ&#10;</run>")
    return f"<customized-tooltip><formatted-text>{''.join(runs)}</formatted-text></customized-tooltip>"


def text_sheet(name: str, ds: str, lines: list[tuple[str, dict]], *, by_param: bool, title: str = "",
               color_field: str | None = None, cell_w: int = 300, cell_h: int = 100) -> str:
    """A single text mark built from several fields, each with its own font — for headers and KPI tiles.
    lines: [(field or literal, {"size":.., "bold":.., "color":..}), ...]; literal strings start with '='."""
    fields: list[tuple[str, str, str]] = []
    runs = []
    for item, fmt in lines:
        attrs = f"fontname='{FONT}' fontsize='{fmt.get('size', 10)}'"
        if fmt.get("bold"):
            attrs += " bold='true'"
        if fmt.get("color"):
            attrs += f" fontcolor='{fmt['color']}'"
        if item.startswith("="):
            runs.append(f"<run {attrs}>{escape(rtl(item[1:]))}</run>")
        else:
            fields.append((item, "string", "nk"))
            runs.append(f"<run {attrs}>&lt;{inst(ds, item)}&gt;</run>")
        if fmt.get("br", True):
            runs.append("<run>Æ&#10;</run>")
    if not fields:  # literal-only label (the back button) still needs one mark to draw on
        fields.append((read_header(ds)[0], "string", "nk"))
        enc = f"              <text column='{inst(ds, fields[0][0])}' />"
    else:
        enc = "\n".join(f"              <text column='{inst(ds, f)}' />" for f, _, _ in fields)
    if color_field:
        fields.append((color_field, "string", "nk"))
        enc += f"\n              <color column='{inst(ds, color_field)}' />"
    filters = ""
    slices = ""
    if by_param:
        fields.append(("is_selected", "boolean", "nk"))
        filters = member_filter(ds, "is_selected", "true", quoted=False)
        slices = f"<slices><column>{inst(ds, 'is_selected')}</column></slices>"
    return f"""    <worksheet name={q(name)}>
{title_xml(title) if title else ''}
      <table>
        <view>
          <datasources>
            <datasource caption='{ds}' name='{ds_name(ds)}' />
          </datasources>
{deps(ds, fields)}
{filters}
          {slices}
          <aggregation value='true' />
        </view>
        <style>
          <style-rule element='cell'>
            <format attr='text-align' value='right' />
            <format attr='vertical-align' value='top' />
            <format attr='cell-w' value='{cell_w}' />
            <format attr='cell-h' value='{cell_h}' />
            <format attr='cell' value='20' />
            <format attr='cell-q' value='100' />
          </style-rule>
        </style>
        <panes>
          <pane selection-relaxation-option='selection-relaxation-allow'>
            <view>
              <breakdown value='auto' />
            </view>
            <mark class='Text' />
            <encodings>
{enc}
            </encodings>
            <customized-tooltip show-buttons='false'><formatted-text><run /></formatted-text></customized-tooltip>
            <customized-label>
              <formatted-text>
                {''.join(runs)}
              </formatted-text>
            </customized-label>
            <style>
              <style-rule element='mark'>
                <format attr='mark-labels-show' value='true' />
                <format attr='text-align' value='right' />
              </style-rule>
            </style>
          </pane>
        </panes>
        <rows />
        <cols />
      </table>
      {simple_id(name)}
    </worksheet>"""


def bar_sheet(name: str, ds: str, order_field: str, value_field: str, label_field: str, color_field: str,
              title: str) -> str:
    """Horizontal bars that grow right-to-left (reversed axis), labelled in words; row headers hidden."""
    calc = f"{value_field}_usd"
    fields = [(order_field, "integer", "ok"), (label_field, "string", "nk"), (color_field, "string", "nk"),
              ("is_selected", "boolean", "nk")]
    dep = deps(ds, fields).replace(
        "          </datasource-dependencies>",
        f"""            <column caption='דולר' datatype='real' name='[{calc}]' role='measure' type='quantitative'>
              <calculation class='tableau' formula='[{value_field}] / 1000000' />
            </column>
            <column-instance column='[{calc}]' derivation='Sum' name='[sum:{calc}:qk]' pivot='key' type='quantitative' />
          </datasource-dependencies>""",
    )
    measure = f"[{ds_name(ds)}].[sum:{calc}:qk]"
    return f"""    <worksheet name={q(name)}>
{title_xml(title)}
      <table>
        <view>
          <datasources>
            <datasource caption='{ds}' name='{ds_name(ds)}' />
          </datasources>
{dep}
{member_filter(ds, "is_selected", "true", quoted=False)}
          <slices><column>{inst(ds, 'is_selected')}</column></slices>
          <aggregation value='true' />
        </view>
        <style>
          <style-rule element='axis'>
            <encoding attr='space' class='0' field='{measure}' field-type='quantitative' reverse='true' scope='cols' type='space' />
            <format attr='display' class='0' field='{measure}' scope='cols' value='false' />
          </style-rule>
          <style-rule element='label'>
            <format attr='display' field='{inst(ds, order_field, "ok")}' value='false' />
          </style-rule>
          <style-rule element='worksheet'>
            <format attr='display-field-labels' scope='rows' value='false' />
            <format attr='display-field-labels' scope='cols' value='false' />
          </style-rule>
          <style-rule element='gridline'>
            <format attr='stroke-size' value='0' />
          </style-rule>
        </style>
        <panes>
          <pane selection-relaxation-option='selection-relaxation-allow'>
            <view>
              <breakdown value='auto' />
            </view>
            <mark class='Bar' />
            <encodings>
              <color column='{inst(ds, color_field)}' />
              <text column='{inst(ds, label_field)}' />
            </encodings>
            {tooltip([(inst(ds, label_field), True)])}
            <style>
              <style-rule element='mark'>
                <format attr='mark-labels-show' value='true' />
                <format attr='mark-labels-cull' value='false' />
                <format attr='font-family' value='{FONT}' />
                <format attr='size' value='0.6' />
              </style-rule>
            </style>
          </pane>
        </panes>
        <rows>{inst(ds, order_field, "ok")}</rows>
        <cols>{measure}</cols>
      </table>
      {simple_id(name)}
    </worksheet>"""


# ---------------------------------------------------------------- dashboards


class Zones:
    """Floating layout in pixels; Tableau stores positions in 1/100000 of the dashboard size."""

    def __init__(self, width: int, height: int):
        self.w, self.h = width, height
        self.items: list[str] = []
        self.sheets: list[str] = []
        self.fit: dict[str, str] = {}
        self.next_id = 10

    def _id(self) -> int:
        self.next_id += 1
        return self.next_id

    def _box(self, x: int, y: int, w: int, h: int) -> str:
        u = lambda v, total: round(v * 100000 / total)  # noqa: E731
        return f"h='{u(h, self.h)}' w='{u(w, self.w)}' x='{u(x, self.w)}' y='{u(y, self.h)}'"

    def sheet(self, name: str, x: int, y: int, w: int, h: int, show_title: bool = True, fit: str | None = None) -> None:
        self.sheets.append(name)
        if fit:
            self.fit[name] = fit
        self.items.append(
            f"<zone floating='true' {self._box(x, y, w, h)} id='{self._id()}' name={q(name)} show-title='{str(show_title).lower()}' />"
        )

    def text(self, runs: list[tuple[str, dict]], x: int, y: int, w: int, h: int) -> None:
        body = []
        for text, fmt in runs:
            attrs = f"fontalignment='2' fontname='{FONT}' fontsize='{fmt.get('size', 10)}'"
            if fmt.get("bold"):
                attrs += " bold='true'"
            attrs += f" fontcolor='{fmt.get('color', INK)}'"
            body.append(f"<run {attrs}>{escape(rtl(text))}</run>")
        self.items.append(
            f"<zone floating='true' {self._box(x, y, w, h)} id='{self._id()}' type-v2='text'>"
            f"<formatted-text>{''.join(body)}</formatted-text></zone>"
        )

    def paramctrl(self, param: str, x: int, y: int, w: int, h: int, mode: str = "compact") -> None:
        self.items.append(
            f"<zone floating='true' {self._box(x, y, w, h)} id='{self._id()}' mode='{mode}' param='{param}' type-v2='paramctrl' />"
        )

    def filter(self, sheet: str, field: str, x: int, y: int, w: int, h: int, mode: str) -> None:
        self.items.append(
            f"<zone floating='true' {self._box(x, y, w, h)} id='{self._id()}' mode='{mode}' name={q(sheet)} param='{field}' type-v2='filter' />"
        )

    def xml(self) -> str:
        return "\n".join("          " + i for i in self.items)


def dashboard(name: str, zones: Zones) -> str:
    return f"""    <dashboard name={q(name)}>
      <style>
        <style-rule element='table'>
          <format attr='background-color' value='#ffffff' />
        </style-rule>
      </style>
      <size maxheight='{zones.h}' maxwidth='{zones.w}' minheight='{zones.h}' minwidth='{zones.w}' sizing-mode='fixed' />
      <zones>
        <zone h='100000' id='1' type-v2='layout-basic' w='100000' x='0' y='0'>
{zones.xml()}
        </zone>
      </zones>
      {simple_id(name)}
    </dashboard>"""


def windows_xml(sheets: list[str], dashboards: dict[str, list[str]], fits: dict[str, str] | None = None) -> str:
    fits = fits or {}
    out = []
    first = next(iter(dashboards), None)
    for n, members in dashboards.items():
        vps = "\n".join(
            f"        <viewpoint name={q(m)}>\n          <zoom type='{fits[m]}' />\n        </viewpoint>" if m in fits
            else f"        <viewpoint name={q(m)} />"
            for m in members
        )
        out.append(f"""    <window class='dashboard' {"maximized='true' " if n == first else ""}name={q(n)}>
      <viewpoints>
{vps}
      </viewpoints>
      <active id='-1' />
      {simple_id('win/' + n)}
    </window>""")
    for n in sheets:
        out.append(f"""    <window class='worksheet' hidden='true' name={q(n)}>
      <cards>
        <edge name='left'>
          <strip size='160'>
            <card type='pages' />
            <card type='filters' />
            <card type='marks' />
          </strip>
        </edge>
        <edge name='top'>
          <strip size='2147483647'>
            <card type='columns' />
          </strip>
          <strip size='2147483647'>
            <card type='rows' />
          </strip>
          <strip size='30'>
            <card type='title' />
          </strip>
        </edge>
      </cards>
      {simple_id('win/' + n)}
    </window>""")
    if not dashboards and out:
        out[0] = out[0].replace("hidden='true'", "maximized='true'", 1)
    return "\n".join(out)


# ---------------------------------------------------------------- assemble

OVERVIEW, DETAIL = "סקירת ריצות", "פרטי ריצה"
S_LIST, S_BACK = "רשימת ריצות", "חזרה"
S_KPI_SPENT, S_KPI_CRIT, S_KPI_WARN, S_KPI_RUN = "סיכום הוצאה", "סיכום דורש בירור", "סיכום לידיעה", "סיכום פעילות"
S_VERDICT = "פסק הדין"
S_REASONS = "סיבות"
S_HEAD, S_COST, S_BUDGET, S_CEIL, S_AGENTS_BAR, S_AGENTS, S_CALLS, S_EVENTS = (
    "כותרת ריצה", "עלות הריצה", "מצב התקציב", "היסטוריית התקרה", "עלות לפי סוכן", "סוכנים", "קריאות מודל", "ציר אירועים",
)


def build() -> str:
    with (DATA / "runs.csv").open(encoding="utf-8") as f:
        runs = sorted(csv.DictReader(f), key=lambda r: int(r["order_index"]))

    tone_colors = palette_style(("tone", TONES))
    datasources = "\n".join([
        parameters_ds(runs),
        datasource("cells", {"is_selected": SELECTED}, tone_colors),
        datasource("summary"),
        datasource("run_header", {"is_selected": SELECTED}, palette_style(("tone", TONES), ("reasons_tone", TONES))),
        datasource("budget_bars", {"is_selected": SELECTED}, palette_style(("kind", BAR_KINDS))),
        datasource("nodes", {"is_selected": SELECTED}, palette_style(("status_he", {
            "הצליח": "#2f6fb5", "נכשל": "#b42318", "לא הופעל": "#c9ced6", "רץ כעת": "#7aa7da", "ממתין": "#c9ced6"}))),
    ])

    W, M = 1200, 24          # dashboard width (fits a 1280px laptop screen with no horizontal scroll), outer margin
    IW = W - 2 * M           # inner width

    GAP = 16
    KW = (IW - 3 * GAP) // 4   # KPI tile width
    HX = 360                   # detail header: width of the cost tile column on the left

    def cw(cols: int) -> int:
        """Cell width so that `cols` equal columns fill the inner width."""
        return int((IW - 8) / cols * CELL_SCALE)

    worksheets = [
        cells_sheet(S_LIST, "runs_list", by_param=False, cell_w=cw(5), cell_h=84,
                    title="כל הריצות · דורש בירור קודם, ואז מהחדשה לישנה · לחיצה על שורה פותחת את פרטי הריצה"),
        text_sheet(S_KPI_SPENT, "summary", [("=הוצאה כוללת", {"size": 10, "color": MUTED}), ("spent_label", {"size": 19, "bold": True}), ("spent_sub", {"size": 9, "color": MUTED, "br": False})], by_param=False, cell_w=KW - 8, cell_h=100),
        text_sheet(S_KPI_CRIT, "summary", [("=דורשות בירור", {"size": 10, "color": MUTED}), ("critical_label", {"size": 19, "bold": True, "color": TONES["critical"]}), ("critical_sub", {"size": 9, "color": MUTED, "br": False})], by_param=False, cell_w=KW - 8, cell_h=100),
        text_sheet(S_KPI_WARN, "summary", [("=לידיעה", {"size": 10, "color": MUTED}), ("warning_label", {"size": 19, "bold": True, "color": TONES["warning"]}), ("warning_sub", {"size": 9, "color": MUTED, "br": False})], by_param=False, cell_w=KW - 8, cell_h=100),
        text_sheet(S_KPI_RUN, "summary", [("=בריצה כעת", {"size": 10, "color": MUTED}), ("running_label", {"size": 19, "bold": True, "color": TONES["neutral"]}), ("running_sub", {"size": 9, "color": MUTED, "br": False})], by_param=False, cell_w=KW - 8, cell_h=100),
        text_sheet(S_HEAD, "run_header", [
            ("title", {"size": 20, "bold": True, "color": INK}),
            ("run_id_display", {"size": 9, "color": MUTED}),
            ("meta", {"size": 9, "color": MUTED, "br": False}),
        ], by_param=True, cell_w=IW - HX - 8, cell_h=130),
        text_sheet(S_VERDICT, "run_header", [
            ("verdict_label", {"size": 13, "bold": True, "br": False}),
        ], by_param=True, color_field="tone", cell_w=IW - HX - 8, cell_h=36),
        text_sheet(S_REASONS, "run_header", [
            ("reasons", {"size": 10, "br": False}),
        ], by_param=True, color_field="reasons_tone", cell_w=IW - HX - 8, cell_h=76),
        text_sheet(S_COST, "run_header", [
            ("=עלות הריצה", {"size": 10, "color": MUTED}),
            ("cost_big", {"size": 22, "bold": True}),
            ("cost_sub", {"size": 9, "color": MUTED, "br": False}),
        ], by_param=True, cell_w=HX - 24, cell_h=214),
        bar_sheet(S_BUDGET, "budget_bars", "bar_order", "value_micro", "bar_label", "kind",
                  "מצב התקציב · כמה אושר וכמה הוצא"),
        cells_sheet(S_CEIL, "ceiling", by_param=True, cell_w=cw(3), cell_h=30, title="היסטוריית התקרה · כל שורה היא פרק זמן שבו התקרה הייתה בתוקף"),
        bar_sheet(S_AGENTS_BAR, "nodes", "node_order", "cost_micro", "bar_label", "status_he",
                  "איפה הכסף נשרף · עלות לפי סוכן"),
        cells_sheet(S_EVENTS, "events", by_param=True, cell_w=cw(4), cell_h=56, title="ציר האירועים · מה קרה ומתי"),
        cells_sheet(S_AGENTS, "agents", by_param=True, cell_w=cw(7), cell_h=72, title="סוכנים · מודל, עלות ונתוני שימוש"),
        cells_sheet(S_CALLS, "calls", by_param=True, cell_w=cw(7), cell_h=60, title="קריאות מודל · עלות מוערכת מול בפועל (כל תור של קריאה בשורה נפרדת)"),
        text_sheet(S_BACK, "summary", [("=→ חזרה לסקירת הריצות", {"size": 11, "bold": True, "color": TONES["neutral"], "br": False})], by_param=False, cell_w=292, cell_h=32),
    ]
    only = os.environ.get("HARA_ONLY")
    if only:
        keep = [int(x) for x in only.split(",")]
        worksheets = [w for i, w in enumerate(worksheets) if i in keep]
    sheet_names = [SHEET_NAME.search(w).group(2) for w in worksheets]
    worksheets = "\n".join(worksheets)

    # ---- overview: title, 4 KPI tiles, filters, the table
    ov = Zones(W, 1450)
    ov.text([("מרכז בקרת ריצות", {"size": 24, "bold": True}),
             ("\nצבע: אדום = דורש בירור · כתום = לידיעה · ירוק = תקין · כחול = בריצה.  סימנים: ! חריגה · ? עלות לא ידועה · ✖ נכשלה · ◑ חלקית · ≠ פער בעלות · ▼ איכות הורדה · ▲ תקציב הורחב · ◔ בריצה · ✔ הצליחה", {"size": 10, "color": MUTED}), ("\nסכומים בדולר (4 ספרות אחרי הנקודה) · זמנים בשעון ישראל", {"size": 10, "color": MUTED})],
            M, 8, IW, 84)
    gap = GAP
    kw = KW
    for i, s in enumerate([S_KPI_SPENT, S_KPI_CRIT, S_KPI_WARN, S_KPI_RUN]):  # first tile on the right
        ov.sheet(s, W - M - (i + 1) * kw - i * gap, 96, kw, 104, show_title=False, fit="fit-width")
    ov.filter(S_LIST, f"[{ds_name('cells')}].[none:status_he:nk]", W - M - 330, 212, 330, 56, mode="dropdown")
    ov.filter(S_LIST, f"[{ds_name('cells')}].[none:tone_he:nk]", W - M - 330 - gap - 330, 212, 330, 56, mode="checkdropdown")
    ov.sheet(S_LIST, M, 276, IW, 1160, fit="fit-width")

    # ---- detail: one run, top to bottom = the order a manager asks the questions
    dt = Zones(W, 1880)
    dt.sheet(S_BACK, W - M - 300, 10, 300, 34, show_title=False, fit="fit-width")
    dt.paramctrl("[Parameters].[pRun]", M, 6, 480, 52)
    dt.sheet(S_HEAD, M + HX, 50, IW - HX, 134, show_title=False, fit="fit-width")
    dt.sheet(S_VERDICT, M + HX, 186, IW - HX, 40, show_title=False, fit="fit-width")
    dt.sheet(S_REASONS, M + HX, 228, IW - HX, 84, show_title=False, fit="fit-width")
    dt.sheet(S_COST, M, 60, HX - 16, 248, show_title=False, fit="fit-width")
    half = (IW - gap) // 2
    dt.sheet(S_BUDGET, W - M - half, 320, half, 230, fit="entire-view")
    dt.sheet(S_AGENTS_BAR, M, 320, half, 230, fit="entire-view")
    dt.sheet(S_CEIL, M, 562, IW, 130, fit="fit-width")
    dt.sheet(S_EVENTS, M, 704, IW, 260, fit="fit-width")
    dt.sheet(S_AGENTS, M, 976, IW, 440, fit="fit-width")
    dt.sheet(S_CALLS, M, 1428, IW, 440, fit="fit-width")

    dashboards = "\n".join([dashboard(OVERVIEW, ov), dashboard(DETAIL, dt)])
    fits = {**ov.fit, **dt.fit}
    actions_off = bool(os.environ.get("HARA_NODASH"))
    if actions_off:
        dashboards = ""

    actions = f"""  <actions>
    <nav-action caption='מעבר לפרטי הריצה' name='[Action1_GoDetail]'>
      <activation auto-clear='true' type='on-select' />
      <source dashboard={q(OVERVIEW)} type='sheet' worksheet={q(S_LIST)} />
      <params>
        <param name='sheet' value={q(DETAIL)} />
        <param name='target' value={q(DETAIL)} />
      </params>
    </nav-action>
    <nav-action caption='חזרה לסקירה' name='[Action2_Back]'>
      <activation auto-clear='true' type='on-select' />
      <source dashboard={q(DETAIL)} type='sheet' worksheet={q(S_BACK)} />
      <params>
        <param name='sheet' value={q(OVERVIEW)} />
        <param name='target' value={q(OVERVIEW)} />
      </params>
    </nav-action>
    <edit-parameter-action caption='בחירת ריצה מהרשימה' name='[Action3_SetRun]'>
      <activation type='on-select' />
      <source dashboard={q(OVERVIEW)} type='sheet' worksheet={q(S_LIST)} />
      <agg-type type='attr' />
      <clear-option type='do-nothing' value='s:LROOT:' />
      <params>
        <param name='source-field' value='{inst("cells", "run_id")}' />
        <param name='target-parameter' value='[Parameters].[pRun]' />
      </params>
    </edit-parameter-action>
  </actions>"""

    return f"""<?xml version='1.0' encoding='utf-8' ?>
<workbook original-version='18.1' source-build='2026.2.3 (20262.26.0912.1023)' source-platform='win' version='18.1' xmlns:user='http://www.tableausoftware.com/xml/user'>
  <document-format-change-manifest>
    <AnimationOnByDefault />
    <MarkAnimation />
    <NavigationAction />
    <ObjectModelEncapsulateLegacy />
    <ObjectModelExtractV2 />
    <ObjectModelTableType />
    <ParameterAction />
    <ParameterActionClearSelection />
    <SchemaViewerObjectModel />
    <SetMembershipControl />
    <SheetIdentifierTracking />
    <VConnDownstreamExtractsWithWarnings />
    <WindowsPersistSimpleIdentifiers />
  </document-format-change-manifest>
  <preferences>
    <preference name='ui.encoding.shelf.height' value='24' />
    <preference name='ui.shelf.height' value='26' />
  </preferences>
  <datasources>
{datasources}
  </datasources>
{"" if actions_off else actions}
  <worksheets>
{worksheets}
  </worksheets>
{"  <dashboards>" + chr(10) + dashboards + chr(10) + "  </dashboards>" if dashboards else ""}
  <windows saved-dpi-scale-factor='1.5' source-height='44'>
{windows_xml(sheet_names, {} if actions_off else {OVERVIEW: ov.sheets, DETAIL: dt.sheets}, fits)}
  </windows>
</workbook>
"""


def package(twbx: Path) -> None:
    """hara-runs.twbx = the workbook + its CSVs + extracts, with relative paths. Opens anywhere."""
    import zipfile

    PATHS.update(csv_dir="Data/data", hyper_dir="Data/Extracts")
    try:
        xml = build()
    finally:
        PATHS.update(csv_dir=DATA.as_posix(), hyper_dir=(HERE / "extracts").as_posix())
    with zipfile.ZipFile(twbx, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("hara-runs.twb", xml)
        for name in DATASOURCES:
            z.write(DATA / f"{name}.csv", f"Data/data/{name}.csv")
            z.write(HERE / "extracts" / f"{name}.hyper", f"Data/Extracts/{name}.hyper")


if __name__ == "__main__":
    for ds in DATASOURCES:
        write_extract(ds, HERE / "extracts")
    (HERE / "hara-runs.twb").write_text(build(), encoding="utf-8")
    package(HERE / "hara-runs.twbx")
    print("built hara-runs.twb and hara-runs.twbx")
