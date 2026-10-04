"""
Turns the frozen JSON fixtures (data/) into flat, Tableau-friendly CSV tables.

Money rule (DATA-CONTRACT.md): *_usd fields are strings and must never be summed as
binary floats. Everything money-related here is parsed with Decimal and stored as an
integer number of micro-dollars (1 USD = 1_000_000). Integer sums are exact, so
Tableau can SUM them safely; dividing by 1e6 happens only for drawing axes.
All user-facing money strings are produced here, from Decimal, in one format.
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

MICRO = Decimal("1000000")
LOCAL_TZ = ZoneInfo("Asia/Jerusalem")

# ---------------------------------------------------------------- formatting


def usd_to_micro(value: str | None) -> int | None:
    if value is None:
        return None
    d = Decimal(value)
    micro = d * MICRO
    if micro != micro.to_integral_value():
        raise ValueError(f"more than 6 decimal places: {value!r}")
    return int(micro)


def fmt_usd(micro: int | None, places: int = 4) -> str:
    """$0.7129 — one format across the whole dashboard. Full precision via places=6."""
    if micro is None:
        return "—"
    d = (Decimal(micro) / MICRO).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    sign = "-" if d < 0 else ""
    return f"{sign}${abs(d):,.{places}f}"


def pct(part_micro: int, whole_micro: int) -> int | None:
    """Integer percent, not capped at 100 (446% must stay 446%)."""
    if not whole_micro:
        return None
    return int((Decimal(part_micro) * 100 / Decimal(whole_micro)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def parse_ts(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def local_str(ts: datetime | None) -> str:
    return ts.astimezone(LOCAL_TZ).strftime("%d.%m.%Y %H:%M") if ts else ""


def local_iso(ts: datetime | None) -> str:
    """Naive local datetime for Tableau (it has no time-zone support for CSV)."""
    return ts.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S") if ts else ""


def fmt_duration(seconds: int | None) -> str:
    if seconds is None:
        return "טרם הסתיימה"
    if seconds < 60:
        return f"{seconds} שנ׳"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} דק׳ {sec} שנ׳" if sec else f"{minutes} דק׳"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} שע׳ {minutes} דק׳"


def ltr(text: str) -> str:
    """Isolate a technical id (run-2c91e7, claude-sonnet-4-6) inside RTL text."""
    return f"⁦{text}⁩"


def agents_not_run(n: int) -> str:
    return "סוכן אחד לא הופעל" if n == 1 else f"{n} סוכנים לא הופעלו"


def fmt_int(n: int | None) -> str:
    return "—" if n is None else f"{n:,}"


def fmt_pct(p):
    return "—" if p is None else f"{p}%"


def fmt_usd_exact(micro):
    text = fmt_usd(micro)
    return fmt_usd(micro, 6) if micro and text.endswith("$0.0000") else text


def fmt_offset(seconds):
    number, _, unit = fmt_duration(abs(seconds)).partition(" ")
    return ltr(("-" if seconds < 0 else "+") + number) + " " + unit


def known(value, default="?"):
    return default if value is None else value


def exceeds(value, cap):
    return isinstance(value, int) and isinstance(cap, int) and value > cap


# ---------------------------------------------------------------- vocab

STATUS_HE = {
    "pending": "ממתינה",
    "running": "בריצה",
    "completed": "הושלמה",
    "partial": "הושלמה חלקית",
    "failed": "נכשלה",
}
OUTCOME_HE = {"succeeded": "הצליחה", "partial": "חלקית", "failed": "נכשלה", None: "טרם נקבעה"}
NODE_STATUS_HE = {"pending": "לא הופעל", "running": "רץ כעת", "succeeded": "הצליח", "failed": "נכשל"}
ROLE_HE = {
    "research": "מחקר",
    "analysis": "ניתוח",
    "reporter": "כתיבת דוח",
    "critic": "ביקורת",
    "team_lead": "ראש צוות",
    "custom": "מותאם",
}
TIER_HE = {"orchestrator": "מתזמר", "worker": "מבצע", "critic": "מבקר"}
REASON_HE = {"initial_approval": "אישור ראשוני", "mid_run_extension_approved": "הרחבה שאושרה באמצע הריצה"}

EVENT_HE = {
    "budget_reserved": "שוריין תקציב",
    "budget_overrun_80": "עברה 80% מהתקרה",
    "budget_hard_stop_95": "עצירה קשה ב-95%",
    "budget_exhausted": "התקציב מוצה",
    "budget_overrun_detected": "חריגה מהתקרה",
    "budget_ceiling_extended": "התקרה הועלתה",
    "approval_requested": "בקשת אישור",
    "approval_resolved": "בקשה אושרה",
    "approval_denied": "בקשה נדחתה",
    "execution_cap_downgraded": "איכות הורדה",
    "web_search_performed": "חיפושי רשת",
    "llm_call": "קריאת מודל",
    "llm_call_failed": "קריאת מודל נכשלה",
    "process_terminated": "התהליך מת",
    "budget_reservation_unresolved": "שריון לא סוכם",
}
# critical = needs a human; warning = worth knowing; info = routine
EVENT_SEVERITY = {
    "budget_reserved": "info",
    "budget_overrun_80": "warning",
    "budget_hard_stop_95": "critical",
    "budget_exhausted": "critical",
    "budget_overrun_detected": "critical",
    "budget_ceiling_extended": "warning",
    "approval_requested": "warning",
    "approval_resolved": "info",
    "approval_denied": "critical",
    "execution_cap_downgraded": "warning",
    "web_search_performed": "info",
    "llm_call": "info",
    "llm_call_failed": "critical",
    "process_terminated": "critical",
    "budget_reservation_unresolved": "critical",
}
SEVERITY_HE = {"critical": "חמור", "warning": "לתשומת לב", "info": "שגרתי"}
SEVERITY_ICON = {"critical": "✖", "warning": "⚠", "info": "●"}

# ---------------------------------------------------------------- verdicts
# One primary verdict per run (what the list shows first) + every reason that applies.

VERDICTS = {
    #  key                label                          tone        icon
    "pending":        ("ממתינה — טרם התחילה",           "neutral",  "○"),
    "cost_unknown":   ("עלות לא ידועה — דורש התאמה",    "critical", "?"),
    "overrun":        ("חריגה מהתקרה",                   "critical", "!"),
    "running":        ("בריצה — טרם הסתיימה",           "neutral",  "◔"),
    "failed":         ("נכשלה",                          "critical", "✖"),
    "partial":        ("הושלמה חלקית",                   "critical", "◑"),
    "cost_gap":       ("פער לא מוסבר בעלות",             "critical", "≠"),
    "needs_review":   ("דורש בירור",                     "critical", "!"),
    "no_outcome":     ("הושלמה, תוצאה לא ידועה",         "warning",  "?"),
    "downgraded":     ("הצליחה, באיכות מופחתת",          "warning",  "▼"),
    "extended":       ("הצליחה, אחרי הרחבת תקציב",       "warning",  "▲"),
    "succeeded":      ("הצליחה",                         "ok",       "✔"),
}
PARTIAL_EXHAUSTED_HE = "חלקית — התקציב מוצה"
TONE_HE = {"critical": "דורש בירור", "warning": "לידיעה", "ok": "תקין", "neutral": "בתהליך"}
TONE_ORDER = {"critical": 0, "warning": 1, "neutral": 2, "ok": 3}
REASON_ICON = {"critical": "✖", "warning": "⚠", "info": "ⓘ"}
REASONS_TONE = {"critical": "critical", "warning": "warning", "info": "muted", None: "ok"}


@dataclass
class RunSignals:
    extended: bool = False
    extension_micro: int = 0
    extension_by: str | None = None
    downgrade_count: int = 0
    downgrade_details: list[str] = field(default_factory=list)
    overrun: bool = False
    cost_unknown: bool = False
    unresolved_micro: int = 0
    open_reservation_micro: int = 0
    budget_exhausted: bool = False
    nodes_not_run: int = 0
    approval_denied: bool = False
    denied_on_timeout: bool = False
    failed: bool = False
    failure_reason: str | None = None
    running: bool = False
    pending: bool = False
    outcome: str | None = None
    cost_gap_micro: int = 0
    nodes_missing_usage: list[str] = field(default_factory=list)


def derive_signals(summary: dict, detail: dict) -> RunSignals:
    s = RunSignals()
    initial = usd_to_micro(summary["initial_budget_usd"])
    approved = usd_to_micro(summary["approved_budget_usd"])
    spent = usd_to_micro(summary["spent_usd"])
    names = {n["node_id"]: n["agent_name"] for n in detail.get("nodes", [])}

    s.extended = approved > initial
    s.extension_micro = approved - initial
    s.overrun = spent > approved
    s.cost_unknown = not summary["cost_is_complete"]
    s.running = summary["status"] == "running"
    s.pending = summary["status"] == "pending"
    s.outcome = summary.get("outcome")
    s.failed = summary["status"] == "failed" or s.outcome == "failed"
    unresolved_ops = set()

    for ev in detail.get("events", []):
        p = ev.get("payload") or {}
        t = ev["type"]
        if t == "approval_resolved" and p.get("decision") == "approved":
            s.extension_by = p.get("by")
        elif t == "execution_cap_downgraded":
            s.downgrade_count += 1
            who = names.get(p.get("node_id"), p.get("node_id"))
            if "from_searches" in p:
                s.downgrade_details.append(f"{who}: חיפושים {p['from_searches']}←{p['to_searches']}")
            elif "from_max_tokens" in p:
                s.downgrade_details.append(f"{who}: אורך פלט {p['from_max_tokens']:,}←{p['to_max_tokens']:,} טוקנים")
        elif t == "budget_overrun_detected":
            s.overrun = True
        elif t == "budget_reservation_unresolved":
            s.cost_unknown = True
            s.unresolved_micro += usd_to_micro(p.get("reserved_usd")) or 0
            unresolved_ops.add(p.get("operation_id"))
        elif t == "budget_exhausted":
            s.budget_exhausted = True
            s.nodes_not_run = p.get("remaining_nodes") or 0
        elif t == "approval_denied" and not s.approval_denied:
            s.approval_denied = True
            s.denied_on_timeout = p.get("reason") == "timeout_no_response"
        elif t == "llm_call_failed" and s.failure_reason is None:
            s.failure_reason = p.get("error")
        elif t == "process_terminated" and s.failure_reason is None:
            s.failure_reason = "התהליך מת באמצע קריאה למודל"

    unsettled = [o for o in detail.get("operations", []) if not o["settled"]]
    if unsettled and not s.running:
        s.cost_unknown = True
    s.open_reservation_micro = s.unresolved_micro + sum(
        usd_to_micro(o["estimated_usd"]) for o in unsettled if o["operation_id"] not in unresolved_ops
    )

    nodes = detail.get("nodes", [])
    if nodes:
        node_sum = sum(usd_to_micro(n["cost_usd"]) for n in nodes)
        s.cost_gap_micro = spent - node_sum
    op_nodes = {o["node_id"] for o in detail.get("operations", [])}
    s.nodes_missing_usage = [
        n["node_id"] for n in nodes if usd_to_micro(n["cost_usd"]) > 0 and n["node_id"] not in op_nodes
    ]
    return s


def primary_verdict(summary: dict, s: RunSignals) -> str:
    if s.pending:
        return "pending"
    if s.cost_unknown:
        return "cost_unknown"
    if s.overrun:
        return "overrun"
    if s.running:
        return "running"
    if s.failed:
        return "failed"
    if summary["status"] == "partial" or s.outcome == "partial" or s.budget_exhausted:
        return "partial"
    if s.cost_gap_micro:
        return "cost_gap"
    if s.approval_denied:
        return "needs_review"
    if s.outcome != "succeeded":
        return "no_outcome"
    if s.downgrade_count:
        return "downgraded"
    if s.extended:
        return "extended"
    return "succeeded"


def attention_reasons(summary: dict, s: RunSignals) -> list[tuple[str, str]]:
    """(tone, text) — every reason a manager should look at this run, most severe first."""
    spent = usd_to_micro(summary["spent_usd"])
    approved = usd_to_micro(summary["approved_budget_usd"])
    initial = usd_to_micro(summary["initial_budget_usd"])
    out: list[tuple[str, str]] = []
    if s.cost_unknown:
        out.append((
            "critical",
            f"עלות לא סופית: {fmt_usd(s.open_reservation_micro)} שוריינו ולא סוכמו — לא ידוע אם חויבנו "
            "(והעלות עשויה להיות גבוהה יותר)" if s.open_reservation_micro
            else f"עלות לא סופית: {fmt_usd(spent)} הוא חסם תחתון בלבד",
        ))
    if s.overrun:
        out.append(("critical", f"ההוצאה {fmt_usd(spent)} עברה את התקרה {fmt_usd(approved)} ({fmt_pct(pct(spent, approved))})"))
    if s.cost_gap_micro:
        out.append((
            "critical",
            f"פער לא מוסבר של {fmt_usd_exact(abs(s.cost_gap_micro))} בין העלות המדווחת לסכום עלויות הסוכנים",
        ))
    if s.failed:
        out.append(("critical", f"הריצה נכשלה: {ltr(s.failure_reason)}" if s.failure_reason else "הריצה נכשלה"))
    if s.approval_denied:
        out.append(("critical", "בקשה להרחבת תקציב לא נענתה (פג הזמן)" if s.denied_on_timeout
                    else "בקשה להרחבת תקציב נדחתה"))
    if s.budget_exhausted:
        out.append(("critical", f"התקציב מוצה — {agents_not_run(s.nodes_not_run)}"))
    if s.downgrade_count:
        out.append(("warning", "איכות הורדה כדי להיכנס לתקציב: " + "; ".join(s.downgrade_details)))
    if s.extended:
        by = f" (אישר: {s.extension_by})" if s.extension_by else ""
        out.append((
            "warning",
            f"התקרה הורחבה באמצע הריצה מ-{fmt_usd(initial)} ל-{fmt_usd(approved)}{by}; "
            f"ההוצאה היא {fmt_pct(pct(spent, initial))} מהתקציב המקורי",
        ))
    if s.nodes_missing_usage:
        out.append(("info", "לחלק מהסוכנים אין רשומות קריאה — נתוני שימוש חסרים"))
    timeout = re.search(r"after (\d+)s", s.failure_reason or "")
    started, ended = parse_ts(summary["started_at"]), parse_ts(summary["ended_at"])
    if timeout and started and ended and int(timeout.group(1)) > (ended - started).total_seconds():
        out.append((
            "info",
            f"שגיאת timeout של {timeout.group(1)} שנ׳ אינה תואמת משך ריצה של "
            f"{int((ended - started).total_seconds())} שנ׳ — אי-התאמה בנתונים",
        ))
    return out


# ---------------------------------------------------------------- tables


def load(data_dir: Path) -> tuple[list[dict], dict[str, dict]]:
    runs = json.loads((data_dir / "runs.json").read_text(encoding="utf-8"))["runs"]
    details = {}
    for r in runs:
        p = data_dir / "runs" / f"{r['run_id']}.json"
        details[r["run_id"]] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    return runs, details


def build_runs_table(runs: list[dict], details: dict[str, dict]) -> list[dict]:
    rows = []
    for r in runs:
        s = derive_signals(r, details.get(r["run_id"], {}))
        initial = usd_to_micro(r["initial_budget_usd"])
        approved = usd_to_micro(r["approved_budget_usd"])
        spent = usd_to_micro(r["spent_usd"])
        started, ended = parse_ts(r["started_at"]), parse_ts(r["ended_at"])
        duration = int((ended - started).total_seconds()) if started and ended else None
        v = primary_verdict(r, s)
        label, tone, icon = VERDICTS[v]
        if v == "partial" and s.budget_exhausted:
            label = PARTIAL_EXHAUSTED_HE
        reasons = attention_reasons(r, s)
        if v == "running" and any(t == "critical" for t, _ in reasons):
            tone = "critical"
        worst = next((t for t in ("critical", "warning", "info") if any(rt == t for rt, _ in reasons)), None)
        # the headline cost cell: a lower bound must look like one
        spent_label = f"לפחות {fmt_usd(spent)}" if s.cost_unknown else fmt_usd(spent)
        pct_label = f"לפחות {fmt_pct(pct(spent, approved))}" if s.cost_unknown else fmt_pct(pct(spent, approved))
        if s.running:
            pct_label += " (עד כה)"
        rows.append({
            "run_id": r["run_id"],
            "run_id_display": ltr(r["run_id"]),
            "title": r["title"],
            "requested_by": r["requested_by"],
            "status": r["status"],
            "status_he": STATUS_HE.get(r["status"], r["status"]),
            "outcome": r["outcome"] or "",
            "outcome_he": OUTCOME_HE.get(r["outcome"], r["outcome"]),
            "verdict": v,
            "verdict_he": label,
            "verdict_icon": icon,
            "verdict_label": f"{icon} {label}",
            "tone": tone,
            "tone_he": TONE_HE[tone],
            "sort_rank": TONE_ORDER[tone],
            "needs_attention": int(tone == "critical"),
            "attention_reasons": " • ".join(t for _, t in reasons),
            "attention_tones": " • ".join(tone_ for tone_, _ in reasons),
            "reasons_tone": REASONS_TONE[worst],
            "attention_count": sum(1 for tone_, _ in reasons if tone_ != "info"),
            "initial_micro": initial,
            "approved_micro": approved,
            "spent_micro": spent,
            "open_reservation_micro": s.open_reservation_micro,
            "unresolved_micro": s.unresolved_micro,
            "extension_micro": s.extension_micro,
            "remaining_micro": approved - spent,
            "pct_of_approved": pct(spent, approved),
            "pct_of_initial": pct(spent, initial),
            "initial_label": fmt_usd(initial),
            "approved_label": fmt_usd(approved),
            "spent_label": spent_label,
            "spent_full": fmt_usd(spent, 6),
            "pct_label": pct_label,
            "budget_label": (
                f"{fmt_usd(approved)} (במקור {fmt_usd(initial)})" if s.extended else fmt_usd(approved)
            ),
            "cost_is_complete": int(not s.cost_unknown),
            "is_extended": int(s.extended),
            "is_overrun": int(s.overrun),
            "is_downgraded": int(bool(s.downgrade_count)),
            "is_running": int(s.running),
            "downgrade_count": s.downgrade_count,
            "cost_gap_micro": s.cost_gap_micro,
            "started_utc": r["started_at"] or "",
            "started_local": local_iso(started),
            "started_label": local_str(started),
            "ended_local": local_iso(ended),
            "ended_label": local_str(ended) or "טרם הסתיימה",
            "duration_sec": duration if duration is not None else "",
            "duration_label": fmt_duration(duration),
            "agent_count": r["agent_count"],
        })
    return rows


def build_nodes_table(runs: list[dict], details: dict[str, dict]) -> list[dict]:
    rows = []
    for r in runs:
        d = details.get(r["run_id"], {})
        run_spent = usd_to_micro(r["spent_usd"])
        run_active = r["status"] in ("running", "pending")
        run_cost_final = not derive_signals(r, d).cost_unknown
        reserved = {}
        failed_call_nodes = set()
        for ev in d.get("events", []):
            p = ev.get("payload") or {}
            if ev["type"] == "budget_reservation_unresolved":
                reserved[p.get("operation_id")] = usd_to_micro(p.get("reserved_usd")) or 0
            elif ev["type"] in ("llm_call_failed", "process_terminated"):
                failed_call_nodes.add(p.get("node_id"))
        ops_by_node: dict[str, list[dict]] = {}
        for o in d.get("operations", []):
            ops_by_node.setdefault(o["node_id"], []).append(o)
        for node_order, n in enumerate(d.get("nodes", []), start=1):
            cost = usd_to_micro(n["cost_usd"])
            ops = ops_by_node.get(n["node_id"], [])
            settled = [o for o in ops if o["settled"] and o["usage"]]
            usage = lambda k: sum(o["usage"][k] for o in settled) if settled else None  # noqa: E731
            est = sum(usd_to_micro(o["estimated_usd"]) for o in ops) if ops else None
            unsettled = [o for o in ops if not o["settled"]]
            open_micro = sum(reserved.get(o["operation_id"], usd_to_micro(o["estimated_usd"])) for o in unsettled)
            cost_unknown = bool(unsettled) and r["status"] != "running"
            started, ended = parse_ts(n["started_at"]), parse_ts(n["ended_at"])
            status_he = "ממתין" if n["status"] == "pending" and run_active else NODE_STATUS_HE.get(n["status"], n["status"])
            if not ops and n["node_id"] in failed_call_nodes:
                usage_note, note_tone = "קריאת מודל נכשלה — אין רשומת קריאה ונתוני שימוש", "critical"
            elif cost > 0 and not ops:
                usage_note, note_tone = "אין רשומות קריאה לסוכן הזה — נתוני שימוש חסרים", "warning"
            elif cost_unknown:
                usage_note = ("קריאה אחת לא סוכמה" if len(unsettled) == 1 else f"{len(unsettled)} קריאות לא סוכמו") \
                    + " — עלות ושימוש לא ידועים"
                note_tone = "critical"
            elif unsettled:
                usage_note = "קריאה אחת בתהליך — טרם סוכמה" if len(unsettled) == 1 \
                    else f"{len(unsettled)} קריאות בתהליך — טרם סוכמו"
                note_tone = "neutral"
            elif not ops and (n["status"] == "running" or status_he == "ממתין"):
                usage_note, note_tone = "טרם בוצעו קריאות", "neutral"
            elif not ops:
                usage_note, note_tone = "לא בוצעו קריאות", "warning"
            else:
                usage_note, note_tone = "", "plain"
            share = pct(cost, run_spent) if run_spent and not cost_unknown else None
            share_label = "" if share is None else f"{share}%" + ("" if run_cost_final else " מהעלות הידועה")
            cost_display = f"לא ידוע (שוריינו {fmt_usd(open_micro)})" if cost_unknown else fmt_usd(cost)
            name = n["agent_name"] if len(n["agent_name"]) <= 22 else n["agent_name"][:21].rstrip() + "…"
            rows.append({
                "run_id": r["run_id"],
                "node_id": n["node_id"],
                "node_order": node_order,
                "agent_name": n["agent_name"],
                "bar_label": f"{name}: {cost_display}"
                + (f" · {share_label}" if share_label else "")
                + ("" if n["status"] == "succeeded" else f" ({status_he})"),
                "role_he": ROLE_HE.get(n["role"], n["role"]),
                "tier_he": TIER_HE.get(n["tier"], n["tier"]),
                "model": n["model"] or "",
                "model_display": ltr(n["model"]) if n["model"] else "— לא רץ",
                "status_he": status_he,
                "cost_micro": cost,
                "cost_label": fmt_usd(cost),
                "cost_display": cost_display,
                "cost_unknown": int(cost_unknown),
                "share_of_run": pct(cost, run_spent) if run_spent else "",
                "share_label": share_label,
                "estimated_micro": est if est is not None else "",
                "estimated_label": fmt_usd(est),
                "unsettled_reserved_micro": open_micro,
                "op_count": len(ops),
                "input_tokens": usage("input_tokens") if settled else "",
                "output_tokens": usage("output_tokens") if settled else "",
                "cache_read_tokens": usage("cache_read_tokens") if settled else "",
                "web_search_count": usage("web_search_count") if settled else "",
                "usage_note": usage_note,
                "usage_note_tone": note_tone,
                "started_label": local_str(started),
                "ended_label": local_str(ended),
                "duration_label": fmt_duration(int((ended - started).total_seconds())) if started and ended
                else ("טרם התחיל" if not started else "טרם הסתיים"),
                "visible_summary": (n["visible_summary"] or "").replace("; ", "; ‏"),
            })
    return rows


def build_operations_table(runs: list[dict], details: dict[str, dict]) -> list[dict]:
    rows = []
    for r in runs:
        d = details.get(r["run_id"], {})
        names = {n["node_id"]: n["agent_name"] for n in d.get("nodes", [])}
        for o in d.get("operations", []):
            est = usd_to_micro(o["estimated_usd"])
            act = usd_to_micro(o["actual_usd"])
            u = o["usage"] or {}
            call_id, _, turn = o["operation_id"].partition(":t")
            rows.append({
                "run_id": r["run_id"],
                "operation_id": o["operation_id"],
                "operation_display": ltr(o["operation_id"]),
                "call_id": call_id,
                "turn": int(turn) if turn.isdigit() else "",
                "node_id": o["node_id"],
                "agent_name": names.get(o["node_id"], o["node_id"]),
                "settled": int(o["settled"]),
                "settled_he": "סוכם" if o["settled"] else "לא סוכם — לא ידוע",
                "estimated_micro": est,
                "actual_micro": act if act is not None else "",
                "estimated_label": fmt_usd(est),
                "actual_label": fmt_usd(act) if act is not None else "לא ידוע",
                "delta_micro": act - est if act is not None else "",
                "delta_pct": known(pct(act - est, est), "") if act is not None else "",
                "input_tokens": u.get("input_tokens", ""),
                "output_tokens": u.get("output_tokens", ""),
                "cache_read_tokens": u.get("cache_read_tokens", ""),
                "cache_creation_tokens": u.get("cache_creation_tokens", ""),
                "web_search_count": u.get("web_search_count", ""),
                "max_tokens_cap": u.get("max_tokens_cap", ""),
                "max_searches_cap": u.get("max_searches_cap", ""),
                "output_over_cap": int(exceeds(u.get("output_tokens"), u.get("max_tokens_cap"))),
                "searches_over_cap": int(exceeds(u.get("web_search_count"), u.get("max_searches_cap"))),
            })
    return rows


def describe_event(ev: dict, names: dict[str, str]) -> str:
    p = ev.get("payload") or {}
    t = ev["type"]
    who = names.get(p.get("node_id"), p.get("node_id") or "")
    if t == "budget_reserved":
        return f"שוריינו {fmt_usd(usd_to_micro(p.get('amount_usd')))} לקריאה הבאה"
    if t in ("budget_overrun_80", "budget_hard_stop_95"):
        spent, ceil = usd_to_micro(p["spent_usd"]), usd_to_micro(p["ceiling_usd"])
        return f"הוצאו {fmt_usd(spent)} מתוך תקרה של {fmt_usd(ceil)} ({fmt_pct(pct(spent, ceil))})"
    if t == "budget_exhausted":
        return f"התקציב מוצה — {agents_not_run(p.get('remaining_nodes') or 0)}"
    if t == "budget_overrun_detected":
        spent, ceil = usd_to_micro(p["spent_usd"]), usd_to_micro(p["ceiling_usd"])
        return f"ההוצאה בפועל {fmt_usd(spent)} עברה את התקרה {fmt_usd(ceil)} — {fmt_pct(pct(spent, ceil))} מהתקרה"
    if t == "budget_ceiling_extended":
        return f"התקרה הועלתה מ-{fmt_usd(usd_to_micro(p['from_usd']))} ל-{fmt_usd(usd_to_micro(p['to_usd']))}"
    if t == "approval_requested":
        return f"התבקשה הרחבה של {fmt_usd(usd_to_micro(p.get('requested_extension_usd')))}"
    if t == "approval_resolved":
        return f"אושרה על ידי {known(p.get('by'), 'לא ידוע')} אחרי {known(p.get('waited_seconds'))} שניות"
    if t == "approval_denied":
        if p.get("reason") == "timeout_no_response":
            return f"לא התקבל מענה תוך {known(p.get('waited_seconds'))} שניות — הבקשה נדחתה אוטומטית"
        return "הבקשה נדחתה"
    if t == "execution_cap_downgraded":
        if "from_searches" in p:
            return f"{who}: מספר החיפושים הוקטן מ-{p['from_searches']} ל-{p['to_searches']} (לא נשאר מספיק תקציב)"
        if "from_max_tokens" in p:
            return (f"{who}: אורך הפלט הוגבל מ-{p['from_max_tokens']:,} ל-{p['to_max_tokens']:,} טוקנים "
                    "(לא נשאר מספיק תקציב)")
        return f"{who}: היקף העבודה הוקטן"
    if t == "web_search_performed":
        return f"{known(p.get('count'))} חיפושים, {known(p.get('source_count'))} מקורות"
    if t == "llm_call":
        return f"קריאות מודל הושלמו ({known(p.get('turns'))} תורות לפי האירוע)"
    if t == "llm_call_failed":
        return f"{who}: {known(p.get('error'))}"
    if t == "process_terminated":
        return f"{who}: התהליך יצא באמצע קריאה לספק"
    if t == "budget_reservation_unresolved":
        return (f"שוריינו {fmt_usd(usd_to_micro(p.get('reserved_usd')))} ולא סוכמו — ייתכן שהספק חייב "
                "וייתכן שלא. נדרשת התאמה ידנית")
    return json.dumps(p, ensure_ascii=False)


def build_events_table(runs: list[dict], details: dict[str, dict]) -> list[dict]:
    rows = []
    for r in runs:
        d = details.get(r["run_id"], {})
        names = {n["node_id"]: n["agent_name"] for n in d.get("nodes", [])}
        started, ended = parse_ts(r["started_at"]), parse_ts(r["ended_at"])
        for i, ev in enumerate(d.get("events", []), start=1):
            at = parse_ts(ev["at"])
            sev = EVENT_SEVERITY.get(ev["type"], "info")
            rows.append({
                "run_id": r["run_id"],
                "seq": i,
                "at_local": local_iso(at),
                "at_label": at.astimezone(LOCAL_TZ).strftime("%H:%M:%S"),
                "offset_label": fmt_offset(int((at - started).total_seconds())) if started else "",
                "after_end": int(bool(ended and at > ended)),
                "type": ev["type"],
                "type_he": EVENT_HE.get(ev["type"], ev["type"]),
                "severity": sev,
                "severity_he": SEVERITY_HE[sev],
                "severity_icon": SEVERITY_ICON[sev],
                "description": describe_event(ev, names),
            })
    return rows


def build_budget_table(runs: list[dict], details: dict[str, dict]) -> list[dict]:
    """
    Ceiling history as *segments* (from → to), not points. A single approval becomes one
    bar spanning the whole run, so the chart stays readable even with one data point.
    """
    rows = []
    for r in runs:
        d = details.get(r["run_id"], {})
        tl = d.get("budget_timeline", [])
        run_end = parse_ts(r["ended_at"])
        for i, step in enumerate(tl):
            start = parse_ts(step["at"])
            end = parse_ts(tl[i + 1]["at"]) if i + 1 < len(tl) else run_end
            ceiling = usd_to_micro(step["ceiling_usd"])
            rows.append({
                "run_id": r["run_id"],
                "step": i + 1,
                "from_local": local_iso(start),
                "to_local": local_iso(end),
                "from_label": start.astimezone(LOCAL_TZ).strftime("%H:%M:%S"),
                "to_label": end.astimezone(LOCAL_TZ).strftime("%H:%M:%S") if end else "עדיין בתוקף",
                "ceiling_micro": ceiling,
                "ceiling_label": fmt_usd(ceiling),
                "reason_he": REASON_HE.get(step["reason"], step["reason"]),
            })
    return rows


def write_csv(path: Path, rows: list[dict], fieldnames=None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = list(dict.fromkeys([*(fieldnames or []), *(k for row in rows for k in row)]))
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)


HEADER_SAMPLE_RUN = {
    "run_id": "header-sample", "title": "", "requested_by": "", "status": "completed", "outcome": "succeeded",
    "initial_budget_usd": "0", "approved_budget_usd": "0", "spent_usd": "0", "started_at": "2026-01-01T00:00:00Z",
    "ended_at": "2026-01-01T00:00:00Z", "agent_count": 1, "cost_is_complete": True,
}
HEADER_SAMPLE_DETAIL = {
    "nodes": [{"node_id": "n1", "agent_name": "", "role": "custom", "tier": "worker", "model": None,
               "status": "succeeded", "cost_usd": "0", "started_at": None, "ended_at": None, "visible_summary": None}],
    "operations": [{"operation_id": "op:t0", "node_id": "n1", "estimated_usd": "0", "actual_usd": "0", "settled": True,
                    "usage": {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_creation_tokens": 0,
                              "web_search_count": 0, "max_tokens_cap": 0, "max_searches_cap": 0}}],
    "events": [{"at": "2026-01-01T00:00:00Z", "type": "llm_call", "payload": {}}],
    "budget_timeline": [{"at": "2026-01-01T00:00:00Z", "ceiling_usd": "0", "reason": "initial_approval"}],
}


def build_all(data_dir: Path, out_dir: Path) -> dict[str, int]:
    import tableau_views as tv

    tables = build_tables(*load(data_dir))
    tv.embed_rtl(tables)
    sample = build_tables([HEADER_SAMPLE_RUN], {HEADER_SAMPLE_RUN["run_id"]: HEADER_SAMPLE_DETAIL})
    for name, rows in tables.items():
        write_csv(out_dir / f"{name}.csv", rows, [k for row in sample[name] for k in row])
    return {k: len(v) for k, v in tables.items()}


def build_tables(runs, details):
    import tableau_views as tv

    tables = {
        "runs": tv.order_runs(build_runs_table(runs, details)),
        "nodes": build_nodes_table(runs, details),
        "operations": build_operations_table(runs, details),
        "events": build_events_table(runs, details),
        "budget": build_budget_table(runs, details),
    }
    tables["cells"] = tv.build_list_cells(tables["runs"]) + tv.build_detail_cells(
        tables["runs"], tables["nodes"], tables["operations"], tables["events"], tables["budget"]
    )
    tables["budget_bars"] = tv.build_budget_bars(tables["runs"])
    tables["summary"] = tv.build_summary(tables["runs"])
    tables["run_header"] = tv.build_run_header(tables["runs"])
    return tables


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    print(build_all(root / "data", root / "tableau" / "data"))
