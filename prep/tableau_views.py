"""
Display tables for Tableau.

Tableau has no RTL mode: row headers are always pinned to the left and columns run
left-to-right. Every table in the dashboard is therefore drawn from one long "cells"
table (table, row, column, text) where `col_pos` is numbered so that the FIRST logical
column (the one a Hebrew reader starts from) gets the HIGHEST position = rightmost.
Text is prepared here once, in one format, and unit-tested — Tableau only lays it out.
"""
from __future__ import annotations

from hara_prep import (
    REASON_ICON,
    SEVERITY_ICON,
    ltr,
    TONE_HE,
    TONE_ORDER,
    VERDICTS,
    fmt_int,
    fmt_pct,
    fmt_usd,
    known,
    parse_ts,
    pct,
)

RLM = "‏"  # forces an RTL paragraph for lines that start with a neutral char (bars, digits)
RLE, PDF = "‫", "‬"  # right-to-left embedding … pop


def rtl_lines(text: str) -> str:
    """
    Tableau Desktop picks the paragraph direction from the text, but Tableau on the web draws every
    label as a left-to-right paragraph: "השוואת … ל-RAG" comes out as "RAG-השוואת … ל" and a leading
    icon jumps to the end. Wrapping each line in an explicit RTL embedding fixes both renderers.
    Technical ids inside keep their own LTR isolate (see hara_prep.ltr).
    """
    if not text:
        return text
    return "\n".join(f"{RLE}{line}{PDF}" if line else line for line in text.split("\n"))


# display text columns per table. Filter values, ids and palette keys stay plain on purpose.
RTL_COLUMNS = {
    "cells": ("text", "col_header"),
    "run_header": ("title", "verdict_label", "meta", "reasons", "cost_big", "cost_sub"),
    "summary": ("spent_label", "spent_sub", "approved_label", "critical_label", "critical_sub",
                "warning_label", "warning_sub", "running_label", "running_sub", "ok_label", "ok_sub"),
    "budget_bars": ("bar_label",),
    "nodes": ("bar_label", "cost_display", "share_label"),
}


def embed_rtl(tables: dict[str, list[dict]]) -> None:
    """Last step before writing CSVs: apply rtl_lines to every display column (in place)."""
    for table, columns in RTL_COLUMNS.items():
        for row in tables.get(table, []):
            for col in columns:
                if isinstance(row.get(col), str):
                    row[col] = rtl_lines(row[col])


def meter(percent: int | None, cells: int = 10) -> str:
    """Text meter that reads right-to-left inside an RTL paragraph. Over 100% is marked, not clipped."""
    if percent is None:
        return ""
    filled = max(0, min(cells, (percent * cells + 50) // 100))
    bar = "▰" * filled + "▱" * (cells - filled)
    return bar + (" ◀◀" if percent > 100 else "")


def _cells(table: str, run_id: str, row_order: int, columns: list[tuple[str, str]], tone: str = "plain",
           tones: dict[str, str] | None = None, extra: dict | None = None) -> list[dict]:
    n = len(columns)
    out = []
    for i, (header, text) in enumerate(columns):
        out.append({
            "table": table,
            "run_id": run_id,
            "row_order": row_order,
            "col_pos": n - i,  # first logical column → rightmost
            "col_header": header,
            "text": text,
            "tone": (tones or {}).get(header, tone),
            **(extra or {}),
        })
    return out


def order_runs(runs_rows: list[dict]) -> list[dict]:
    """Attention first (by severity), newest first within the same severity."""
    ordered = sorted(runs_rows, key=lambda r: (TONE_ORDER[r["tone"]], _newest_first(r["started_utc"])))
    for i, r in enumerate(ordered, start=1):
        r["order_index"] = i
    return ordered


def _newest_first(started_utc):
    ts = parse_ts(started_utc or None)
    return -ts.timestamp() if ts else float("-inf")


def reason_lines(r):
    if not r["attention_reasons"]:
        return []
    return [f"{REASON_ICON[t]} {x}" for t, x in zip(r["attention_tones"].split(" • "), r["attention_reasons"].split(" • "))]


def build_list_cells(runs_rows: list[dict]) -> list[dict]:
    out = []
    for r in runs_rows:
        cost_lines = [f"{r['spent_label']} מתוך {r['approved_label']}", RLM + f"{meter(r['pct_of_approved'])}  {r['pct_label']}"]
        if r["is_extended"]:
            cost_lines.append(f"▲ מקורי {r['initial_label']} · נוצלו {fmt_pct(r['pct_of_initial'])}")
        if not r["cost_is_complete"]:
            cost_lines.append(f"? עוד {fmt_usd(r['open_reservation_micro'])} בשריון פתוח"
                              if r["open_reservation_micro"] else "? חסם תחתון בלבד")
        reasons = reason_lines(r)
        cost_tone = "critical" if (r["is_overrun"] or not r["cost_is_complete"]) else (
            "warning" if r["is_extended"] else "plain")
        out += _cells(
            "runs_list", r["run_id"], r["order_index"],
            [
                ("ריצה", f"{r['title']}\n{r['run_id_display']}"),
                ("פסק דין", f"{r['verdict_label']}\n{RLM}מצב: {r['status_he']} · תוצאה: {r['outcome_he']}"),
                ("עלות מול תקציב", "\n".join(cost_lines)),
                ("למה לשים לב", "\n".join(reasons) if reasons else "—"),
                ("מתי ומי", f"{ltr(r['started_label'])}\n{RLM}משך: {r['duration_label']}\nביקש/ה: {r['requested_by']}"),
            ],
            tones={"פסק דין": r["tone"], "עלות מול תקציב": cost_tone,
                   "למה לשים לב": r["reasons_tone"] if reasons else "plain"},
            extra={"status_he": r["status_he"], "tone_he": r["tone_he"], "title": r["title"]},
        )
    return out


def build_detail_cells(runs_rows, nodes, operations, events, budget) -> list[dict]:
    out: list[dict] = []
    for r in runs_rows:
        rid = r["run_id"]

        # ---- agents: who spent what, on which model, with how much usage
        run_nodes = [n for n in nodes if n["run_id"] == rid]
        if not run_nodes:
            out += _cells("agents", rid, 1, [("סוכן", "לא נרשמו סוכנים בריצה הזו")], tone="muted")
        for i, n in enumerate(run_nodes, start=1):
            tokens = "—" if n["input_tokens"] == "" else (
                f"קלט {fmt_int(n['input_tokens'])}\n{RLM}פלט {fmt_int(n['output_tokens'])}\n"
                f"{RLM}מטמון {fmt_int(n['cache_read_tokens'])}"
            )
            note = "\n".join(x for x in (n["visible_summary"], n["usage_note"]) if x) or "—"
            share = f" · {n['share_label']}" if n["share_label"] else ""
            status_tone = {"נכשל": "critical", "לא הופעל": "warning", "רץ כעת": "neutral",
                           "ממתין": "neutral"}.get(n["status_he"], "plain")
            out += _cells("agents", rid, i, [
                ("סוכן", f"{n['agent_name']}\n{RLM}{n['role_he']} · {n['tier_he']}"),
                ("מודל", n["model_display"]),
                ("מצב", n["status_he"]),
                ("עלות", f"{n['cost_display']}{share}"),
                ("טוקנים", tokens),
                ("חיפושים", "—" if n["web_search_count"] == "" else str(n["web_search_count"])),
                ("הערות", note),
            ], tones={"מצב": status_tone, "עלות": "critical" if n["cost_unknown"] else "plain",
                      "הערות": n["usage_note_tone"]})

        # ---- model calls: estimated vs actual, per turn
        run_ops = [o for o in operations if o["run_id"] == rid]
        if not run_ops:
            out += _cells("calls", rid, 1, [("קריאה", "לא בוצעו קריאות מודל שסוכמו בריצה הזו")], tone="muted")
        for i, o in enumerate(run_ops, start=1):
            if o["delta_micro"] == "":
                delta, delta_tone = "לא ידוע", "critical"
            elif o["delta_pct"] == "":
                delta, delta_tone = "—", "warning" if o["delta_micro"] > 0 else "plain"
            else:
                d = o["delta_micro"]
                sign = "+" if d > 0 else ""
                delta = ltr(f"{sign}{o['delta_pct']}%")  # keep the sign in front, also in RTL
                delta_tone = "critical" if o["delta_pct"] > 50 else ("warning" if d > 0 else "plain")
            usage = "לא התקבלה תשובה מהספק" if not o["settled"] else (
                f"קלט {fmt_int(o['input_tokens'])} · פלט {fmt_int(o['output_tokens'])}\n"
                f"{RLM}מטמון {fmt_int(o['cache_read_tokens'])} · חיפושים {o['web_search_count']}"
            )
            caps = "—" if o["max_tokens_cap"] == "" else (
                f"פלט עד {fmt_int(o['max_tokens_cap'])}\n{RLM}חיפושים עד {known(o['max_searches_cap'], '—')}"
            )
            over_caps = [text for flag, text in ((o["output_over_cap"], "⚠ הפלט חרג מהמגבלה"),
                                                 (o["searches_over_cap"], "⚠ החיפושים חרגו מהמגבלה")) if flag]
            caps += "".join(f"\n{RLM}{x}" for x in over_caps)
            cache_eff = ""
            if o["settled"] and o["input_tokens"] != "":
                total_in = o["input_tokens"] + o["cache_read_tokens"]
                cache_eff = f"{pct(o['cache_read_tokens'], total_in) or 0}%" if total_in else "—"
            out += _cells("calls", rid, i, [
                ("קריאה", f"{o['operation_display']}\n{RLM}{o['agent_name']} · תור {o['turn']}"),
                ("הערכה", o["estimated_label"]),
                ("בפועל", o["actual_label"]),
                ("סטייה", delta),
                ("שימוש", usage),
                ("קלט מהמטמון", cache_eff or "—"),
                ("מגבלות שהוגדרו", caps),
            ], tones={"בפועל": "critical" if not o["settled"] else "plain", "סטייה": delta_tone,
                      "שימוש": "critical" if not o["settled"] else "plain",
                      "מגבלות שהוגדרו": "warning" if over_caps else "plain"})

        # ---- events timeline
        run_events = [e for e in events if e["run_id"] == rid]
        if not run_events:
            out += _cells("events", rid, 1, [("אירוע", "לא נרשמו אירועים בריצה הזו — אין אישורים, הרחבות, הורדות איכות או חריגות")],
                          tone="muted")
        for e in run_events:
            late = " (אחרי סיום הריצה)" if e["after_end"] else ""
            out += _cells("events", rid, e["seq"], [
                ("שעה", f"{e['at_label']}{late}\n{RLM}{e['offset_label']} מההתחלה"),
                ("חומרה", f"{e['severity_icon']} {e['severity_he']}"),
                ("אירוע", e["type_he"]),
                ("פירוט", e["description"]),
            ], tone=e["severity"] if e["severity"] != "info" else "plain",
               tones={"שעה": ("critical" if e["severity"] == "critical" else "warning") if late else "plain"})

        # ---- ceiling history as segments
        run_budget = [b for b in budget if b["run_id"] == rid]
        if not run_budget:
            out += _cells("ceiling", rid, 1, [("תקרה", "לא נרשמה היסטוריית תקרה")], tone="muted")
        for i, b in enumerate(run_budget, start=1):
            out += _cells("ceiling", rid, i, [
                ("תקרה", b["ceiling_label"]),
                ("סיבה", b["reason_he"]),
                ("בתוקף", f"מ-{b['from_label']} " + ("ועדיין בתוקף" if b["to_label"] == "עדיין בתוקף" else f"עד {b['to_label']}")),
            ], tones={"סיבה": "warning" if i > 1 else "plain"})
    return out


def build_budget_bars(runs_rows: list[dict]) -> list[dict]:
    """
    Budget state as a few comparable bars. Works with one data point, unlike a timeline.
    `value_micro` is exact; the chart divides by 1e6 only to draw.
    """
    out = []
    for r in runs_rows:
        bars = []
        if r["is_extended"]:
            bars.append(("תקציב מקורי", r["initial_micro"], "initial"))
        bars.append(("תקרה מאושרת" + (" (אחרי הרחבה)" if r["is_extended"] else ""), r["approved_micro"], "ceiling"))
        spent_name = "הוצאה בפועל" + (" (עד כה)" if r["is_running"] else "")
        if not r["cost_is_complete"]:
            spent_name = "הוצאה ידועה (חסם תחתון)"
        bars.append((spent_name, r["spent_micro"], "over" if r["is_overrun"] else "spent"))
        if not r["cost_is_complete"] and r["open_reservation_micro"]:
            bars.append(("שריון פתוח — לא ידוע אם חויב", r["open_reservation_micro"], "unknown"))
        for i, (name, value, kind) in enumerate(bars, start=1):
            out.append({
                "run_id": r["run_id"],
                "bar_order": i,
                "bar_name": name,
                "value_micro": value,
                "value_label": fmt_usd(value),
                "kind": kind,
                "bar_label": f"{name}: {fmt_usd(value)}"
                + (f" · {fmt_pct(pct(value, r['approved_micro']))} מהתקרה" if kind in ("spent", "over") else ""),
            })
    return out


def build_summary(runs_rows: list[dict]) -> list[dict]:
    spent = sum(r["spent_micro"] for r in runs_rows)
    approved = sum(r["approved_micro"] for r in runs_rows)
    unknown = [r for r in runs_rows if not r["cost_is_complete"]]
    open_micro = sum(r["open_reservation_micro"] for r in unknown)
    crit = sum(1 for r in runs_rows if r["tone"] == "critical")
    warn = sum(1 for r in runs_rows if r["tone"] == "warning")
    ok = sum(1 for r in runs_rows if r["tone"] == "ok")
    running = sum(1 for r in runs_rows if r["is_running"])
    not_final = []
    if open_micro:
        not_final.append(f"+ {fmt_usd(open_micro)} בשריון פתוח, לא ידוע אם חויב")
    elif unknown:
        not_final.append("עלות אחת לא סופית" if len(unknown) == 1 else f"{len(unknown)} עלויות לא סופיות")
    if running:
        not_final.append("כולל ריצה פעילה" if running == 1 else f"כולל {running} ריצות פעילות")
    return [{
        "spent_label": ("לפחות " if not_final else "") + fmt_usd(spent),
        "spent_sub": " · ".join(not_final) or "כל העלויות סופיות",
        "approved_label": f"מתוך {fmt_usd(approved)} שאושרו "
        + ("בריצה אחת" if len(runs_rows) == 1 else f"ב-{len(runs_rows)} ריצות"),
        "critical_label": f"✖ {crit}",
        "critical_sub": "עלות לא ידועה, חריגה, כישלון או תקציב שמוצה",
        "warning_label": f"▲ {warn}",
        "warning_sub": "הרחבת תקציב או הורדת איכות",
        "running_label": f"◔ {running}",
        "running_sub": "ריצה פעילה" if running == 1 else "ריצות פעילות",
        "ok_count": ok,
        "ok_label": f"✔ {ok}",
        "ok_sub": "ריצה תקינה" if ok == 1 else "ריצות תקינות",
    }]


def build_run_header(runs_rows: list[dict]) -> list[dict]:
    out = []
    for r in runs_rows:
        reasons = reason_lines(r)
        agents = "סוכן אחד" if r["agent_count"] == 1 else f"{r['agent_count']} סוכנים"
        out.append({
            "run_id": r["run_id"],
            "title": r["title"],
            "run_id_display": r["run_id_display"],
            "verdict_label": r["verdict_label"],
            "tone": r["tone"],
            "meta": f"מצב: {r['status_he']} · תוצאה: {r['outcome_he']} · ביקש/ה: {r['requested_by']} · "
                    f"{agents}\n{RLM}התחילה {ltr(r['started_label'])} · משך: {r['duration_label']}",
            "reasons": "\n".join(reasons) if reasons else "✔ אין דבר שדורש תשומת לב",
            "reasons_tone": r["reasons_tone"],
            "cost_big": r["spent_label"],
            "cost_sub": f"מתוך {r['approved_label']} · {r['pct_label']} מהתקרה"
            + (f"\n{RLM}{fmt_pct(r['pct_of_initial'])} מהתקציב המקורי ({r['initial_label']})" if r["is_extended"] else "")
            + (f"\n{RLM}+ {fmt_usd(r['open_reservation_micro'])} בשריון פתוח, לא ידוע אם חויב"
               if not r["cost_is_complete"] and r["open_reservation_micro"] else ""),
        })
    return out
