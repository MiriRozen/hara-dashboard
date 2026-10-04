from pathlib import Path

import pytest

import hara_prep as hp
import tableau_views as tv
from test_hara_prep import mk_detail, mk_ev, mk_op, mk_run, mk_usage

DATA = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def tables():
    runs, details = hp.load(DATA)
    t = {
        "runs": tv.order_runs(hp.build_runs_table(runs, details)),
        "nodes": hp.build_nodes_table(runs, details),
        "operations": hp.build_operations_table(runs, details),
        "events": hp.build_events_table(runs, details),
        "budget": hp.build_budget_table(runs, details),
    }
    t["cells"] = tv.build_list_cells(t["runs"]) + tv.build_detail_cells(
        t["runs"], t["nodes"], t["operations"], t["events"], t["budget"])
    return t


def cells(t, table, run_id):
    return [c for c in t["cells"] if c["table"] == table and c["run_id"] == run_id]


def test_meter_is_not_clipped_over_100():
    assert tv.meter(75) == "▰▰▰▰▰▰▰▰▱▱"
    assert tv.meter(446).endswith("◀◀")
    assert tv.meter(0) == "▱" * 10
    assert tv.meter(None) == ""


def test_meter_rounds_half_up():
    assert tv.meter(25) == "▰▰▰" + "▱" * 7
    assert tv.meter(5) == "▰" + "▱" * 9
    assert tv.meter(4) == "▱" * 10


def test_attention_first_then_newest(tables):
    order = [r["run_id"] for r in tables["runs"]]
    tones = [r["tone"] for r in tables["runs"]]
    assert tones[:5] == ["critical"] * 5
    assert order.index("run-2c91e7") < order.index("run-8f3a1c")  # "for your information" before "ok"
    for tone in ("critical", "ok"):
        same = [r for r in tables["runs"] if r["tone"] == tone]
        assert [r["started_utc"] for r in same] == sorted((r["started_utc"] for r in same), reverse=True)


def test_order_is_by_tone_then_newest_not_by_verdict():
    older_overrun = mk_run(run_id="run-o", started_at="2026-08-01T10:00:00Z", ended_at="2026-08-01T10:10:00Z",
                           initial_budget_usd="0.050000", approved_budget_usd="0.050000")
    newer_failed = mk_run(run_id="run-f", outcome="failed", started_at="2026-08-02T10:00:00Z",
                          ended_at="2026-08-02T10:10:00Z")
    running = mk_run(run_id="run-r", status="running", outcome=None, ended_at=None, started_at="2026-07-01T10:00:00Z")
    ok = mk_run(run_id="run-k", started_at="2026-09-01T10:00:00Z", ended_at="2026-09-01T10:10:00Z")
    runs = [ok, running, older_overrun, newer_failed]
    rows = hp.build_runs_table(runs, {r["run_id"]: mk_detail() for r in runs})
    assert [r["run_id"] for r in tv.order_runs(rows)] == ["run-f", "run-o", "run-r", "run-k"]


def test_order_uses_utc_not_the_local_clock():
    # Israel leaves summer time on 2026-10-25: 02:00 local becomes 01:00, so the local clock runs backwards
    a = mk_run(run_id="run-a", started_at="2026-10-24T22:30:00Z", ended_at="2026-10-24T22:40:00Z")  # 01:30 local
    b = mk_run(run_id="run-b", started_at="2026-10-24T23:10:00Z", ended_at="2026-10-24T23:20:00Z")  # 01:10 local
    rows = hp.build_runs_table([a, b], {"run-a": mk_detail(), "run-b": mk_detail()})
    assert rows[0]["started_local"] > rows[1]["started_local"]  # sorting by local time would get it wrong
    assert [r["run_id"] for r in tv.order_runs(rows)] == ["run-b", "run-a"]


def test_first_logical_column_is_rightmost(tables):
    row = cells(tables, "runs_list", "run-2c91e7")
    by_pos = {c["col_pos"]: c["col_header"] for c in row}
    assert by_pos[max(by_pos)] == "ריצה"
    assert by_pos[min(by_pos)] == "מתי ומי"


def test_list_row_explains_extension_and_downgrade(tables):
    ext = {c["col_header"]: c for c in cells(tables, "runs_list", "run-2c91e7")}
    assert "▲ מקורי $0.3500 · נוצלו 204%" in ext["עלות מול תקציב"]["text"]
    assert all(len(line) <= 34 for line in ext["עלות מול תקציב"]["text"].split("\n"))
    assert ext["פסק דין"]["tone"] == "warning"
    down = {c["col_header"]: c for c in cells(tables, "runs_list", "run-77de40")}
    assert "חיפושים 4←2" in down["למה לשים לב"]["text"]


def test_unknown_cost_row_shows_open_reservation_not_a_maximum(tables):
    row = {c["col_header"]: c for c in cells(tables, "runs_list", "run-9e21d4")}
    text = row["עלות מול תקציב"]["text"]
    assert text.startswith("לפחות $0.2148")
    assert "? עוד $0.2600 בשריון פתוח" in text
    assert all(len(line) <= 34 for line in text.split("\n")), text  # fits the list cell on the web
    assert "עד $" not in text and "$0.4748" not in text
    assert "≥" not in text  # mirrors to ≤ in RTL


def test_list_reasons_get_an_icon_per_reason(tables):
    row = {c["col_header"]: c for c in cells(tables, "runs_list", "run-a1f709")}
    lines = row["למה לשים לב"]["text"].split("\n")
    assert lines[0].startswith("✖ ") and lines[-1].startswith("ⓘ ")
    info_only = {c["col_header"]: c for c in cells(tables, "runs_list", "run-11ab02")}
    assert info_only["למה לשים לב"]["tone"] == "muted"


def test_empty_states_in_detail_tables(tables):
    no_events = cells(tables, "events", "run-8f3a1c")
    assert len(no_events) > 0
    no_events = cells(tables, "events", "run-11ab02")
    assert len(no_events) == 1 and "לא נרשמו אירועים" in no_events[0]["text"]
    no_calls = cells(tables, "calls", "run-a1f709")
    assert len(no_calls) == 1 and "לא בוצעו קריאות" in no_calls[0]["text"]


def test_empty_agents_and_ceiling_tables():
    run = mk_run()
    t = hp.build_tables([run], {run["run_id"]: mk_detail(nodes=[], operations=[], budget_timeline=[])})
    agents = [(c["text"], c["tone"]) for c in t["cells"] if c["table"] == "agents"]
    assert agents == [("לא נרשמו סוכנים בריצה הזו", "muted")]
    ceiling = [(c["text"], c["tone"]) for c in t["cells"] if c["table"] == "ceiling"]
    assert ceiling == [("לא נרשמה היסטוריית תקרה", "muted")]


def test_unsettled_call_is_marked_unknown(tables):
    calls = cells(tables, "calls", "run-9e21d4")
    unknown = [c for c in calls if c["col_header"] == "בפועל" and c["text"] == "לא ידוע"]
    assert len(unknown) == 1 and unknown[0]["tone"] == "critical"


def test_caps_cell_says_set_not_enforced_and_flags_overflow(tables):
    assert not any(c["col_header"] == "מגבלות שנאכפו" for c in tables["cells"])
    caps = [c for c in cells(tables, "calls", "run-2c91e7") if c["col_header"] == "מגבלות שהוגדרו"]
    assert "⚠ הפלט חרג מהמגבלה" in caps[0]["text"] and caps[0]["tone"] == "warning"
    within = [c for c in cells(tables, "calls", "run-8f3a1c") if c["col_header"] == "מגבלות שהוגדרו"]
    assert "⚠" not in within[1]["text"] and within[1]["tone"] == "plain"


def test_searches_over_cap_and_zero_estimate_delta():
    run = mk_run()
    op = mk_op(estimated_usd="0.000000", usage=mk_usage(web_search_count=3, max_searches_cap=1))
    t = hp.build_tables([run], {run["run_id"]: mk_detail(operations=[op])})
    calls = {c["col_header"]: c for c in t["cells"] if c["table"] == "calls"}
    assert "⚠ החיפושים חרגו מהמגבלה" in calls["מגבלות שהוגדרו"]["text"]
    assert "⚠ הפלט" not in calls["מגבלות שהוגדרו"]["text"]
    assert calls["מגבלות שהוגדרו"]["tone"] == "warning"
    assert calls["סטייה"]["text"] == "—"


def test_events_after_run_end_are_tagged_in_the_time_cell(tables):
    times = {c["row_order"]: c for c in cells(tables, "events", "run-6b8823") if c["col_header"] == "שעה"}
    assert "(אחרי סיום הריצה)" in times[3]["text"] and times[3]["tone"] == "critical"
    assert "(אחרי סיום הריצה)" not in times[2]["text"] and times[2]["tone"] == "plain"
    assert hp.ltr("+14") + " דק׳ 35 שנ׳ מההתחלה" in times[3]["text"]


def test_agents_table_wording(tables):
    def col(run_id, header):
        return {c["row_order"]: c for c in cells(tables, "agents", run_id) if c["col_header"] == header}

    status = col("run-5d02b8", "מצב")
    assert (status[3]["text"], status[3]["tone"]) == ("ממתין", "neutral")
    assert (col("run-48ba13", "מצב")[2]["text"], col("run-48ba13", "מצב")[2]["tone"]) == ("לא הופעל", "warning")
    notes = col("run-5d02b8", "הערות")
    assert (notes[2]["text"], notes[2]["tone"]) == ("טרם בוצעו קריאות", "neutral")
    cost = col("run-9e21d4", "עלות")
    assert (cost[2]["text"], cost[2]["tone"]) == ("לא ידוע (שוריינו $0.2600)", "critical")
    assert cost[1]["text"] == "$0.2148 · 100% מהעלות הידועה"
    assert col("run-2c91e7", "עלות")[1]["text"] == "$0.4023 · 56%"
    note = col("run-9e21d4", "הערות")[2]
    assert note["text"].endswith("קריאה אחת לא סוכמה — עלות ושימוש לא ידועים") and note["tone"] == "critical"
    failed = col("run-a1f709", "הערות")[1]
    assert (failed["text"], failed["tone"]) == ("קריאת מודל נכשלה — אין רשומת קריאה ונתוני שימוש", "critical")


def test_ceiling_history_reads_from_to(tables):
    rows = cells(tables, "ceiling", "run-2c91e7")
    validity = [c["text"] for c in rows if c["col_header"] == "בתוקף"]
    assert validity == ["מ-14:02:18 עד 14:09:55", "מ-14:09:55 עד 14:19:44"]
    running = [c["text"] for c in cells(tables, "ceiling", "run-5d02b8") if c["col_header"] == "בתוקף"]
    assert running == ["מ-16:20:11 ועדיין בתוקף"]


def test_budget_bars_show_open_reservation_for_unknown_cost(tables):
    bars = [b for b in tv.build_budget_bars(tables["runs"]) if b["run_id"] == "run-9e21d4"]
    assert [b["kind"] for b in bars] == ["ceiling", "spent", "unknown"]
    assert bars[-1]["value_micro"] == 260_000
    assert bars[-1]["bar_label"] == "שריון פתוח — לא ידוע אם חויב: $0.2600"
    assert not any("מקסימלית" in b["bar_label"] for b in tv.build_budget_bars(tables["runs"]))


def test_rtl_lines_wraps_every_line_in_an_rtl_embedding():
    assert tv.rtl_lines("השוואת מסדי נתונים ל-RAG") == "‫השוואת מסדי נתונים ל-RAG‬"
    assert tv.rtl_lines("א\nב") == "‫א‬\n‫ב‬"
    assert tv.rtl_lines("") == ""


def test_embed_rtl_touches_display_text_only(tables):
    t = {
        "cells": [dict(c) for c in tables["cells"][:3]],
        "summary": tv.build_summary(tables["runs"]),
    }
    tv.embed_rtl(t)
    for c in t["cells"]:
        assert c["text"].startswith("‫")
        assert not c["run_id"].startswith("‫")  # ids / filter keys stay plain
        assert c["tone"] in tv.TONE_HE or c["tone"] in ("plain", "muted")
    assert t["summary"][0]["spent_label"] == "‫לפחות $6.0715‬"
    assert t["summary"][0]["ok_label"].startswith("‫")
    assert "reasons_tone" not in tv.RTL_COLUMNS["run_header"]


def test_summary_is_exact_and_honest(tables):
    s = tv.build_summary(tables["runs"])[0]
    assert s["spent_label"] == "לפחות $6.0715"
    assert s["spent_sub"] == "+ $0.2600 בשריון פתוח, לא ידוע אם חויב · כולל ריצה פעילה"
    assert s["critical_label"] == "✖ 5"
    assert s["critical_sub"] == "עלות לא ידועה, חריגה, כישלון או תקציב שמוצה"
    assert s["warning_label"] == "▲ 2"
    assert s["warning_sub"] == "הרחבת תקציב או הורדת איכות"
    assert s["running_label"] == "◔ 1"
    assert (s["ok_count"], s["ok_label"]) == (5, "✔ 5")


def test_summary_is_not_final_while_a_run_is_running():
    run = mk_run(status="running", outcome=None, ended_at=None)
    s = tv.build_summary(hp.build_runs_table([run], {run["run_id"]: mk_detail()}))[0]
    assert s["spent_label"] == "לפחות $0.1000"
    assert s["spent_sub"] == "כולל ריצה פעילה"
    two = [mk_run(run_id=f"run-{i}", cost_is_complete=False) for i in range(2)]
    s = tv.build_summary(hp.build_runs_table(two, {r["run_id"]: mk_detail() for r in two}))[0]
    assert s["spent_sub"] == "2 עלויות לא סופיות"
    done = [mk_run()]
    s = tv.build_summary(hp.build_runs_table(done, {"run-syn": mk_detail()}))[0]
    assert (s["spent_label"], s["spent_sub"]) == ("$0.1000", "כל העלויות סופיות")


def test_run_header_reason_icons_follow_each_reason(tables):
    h = {r["run_id"]: r for r in tv.build_run_header(tables["runs"])}
    lines = h["run-a1f709"]["reasons"].split("\n")
    assert lines[0].startswith("✖ ") and lines[-1].startswith("ⓘ ")
    assert h["run-a1f709"]["reasons_tone"] == "critical"
    assert h["run-2c91e7"]["reasons"].startswith("⚠ ") and h["run-2c91e7"]["reasons_tone"] == "warning"
    assert h["run-11ab02"]["reasons"].startswith("ⓘ ") and h["run-11ab02"]["reasons_tone"] == "muted"
    assert (h["run-8f3a1c"]["reasons"], h["run-8f3a1c"]["reasons_tone"]) == ("✔ אין דבר שדורש תשומת לב", "ok")


def test_run_header_meta_and_open_reservation(tables):
    h = {r["run_id"]: r for r in tv.build_run_header(tables["runs"])}
    assert "סוכן אחד\n" in h["run-b41055"]["meta"] and "1 סוכנים" not in h["run-b41055"]["meta"]
    assert "4 סוכנים\n" in h["run-2c91e7"]["meta"]
    assert "התחילה " + hp.ltr("18.08.2026 14:02") in h["run-2c91e7"]["meta"]
    assert "$0.2600 בשריון פתוח, לא ידוע אם חויב" in h["run-9e21d4"]["cost_sub"]
    assert "עד $" not in h["run-9e21d4"]["cost_sub"]


def nasty_inputs():
    zero = mk_run(run_id="run-zero", initial_budget_usd="0.000000", approved_budget_usd="0.000000", outcome=None)
    ext = mk_run(run_id="run-ext", initial_budget_usd="0.000000", approved_budget_usd="0.500000",
                 status="running", ended_at=None, outcome=None)
    events = [
        mk_ev("llm_call", turns=None), mk_ev("approval_resolved", decision="approved", by=None, waited_seconds=None),
        mk_ev("web_search_performed"), mk_ev("llm_call_failed", error=None, node_id="n1"),
        mk_ev("budget_overrun_detected", spent_usd="0.100000", ceiling_usd="0.000000"),
        mk_ev("budget_overrun_80", spent_usd="0.100000", ceiling_usd="0.000000"),
        mk_ev("approval_requested"), mk_ev("budget_exhausted"), mk_ev("approval_denied"),
        mk_ev("budget_reserved"), mk_ev("budget_reservation_unresolved"), mk_ev("process_terminated"),
    ]
    detail = mk_detail(operations=[mk_op(estimated_usd="0.000000", usage=mk_usage(max_tokens_cap=None))],
                       events=events)
    return [zero, ext], {"run-zero": detail, "run-ext": mk_detail(operations=[mk_op(settled=False, actual_usd=None,
                                                                                     usage=None)])}


@pytest.mark.parametrize("source", ["real", "nasty"])
def test_no_generated_string_says_none(source):
    runs, details = hp.load(DATA) if source == "real" else nasty_inputs()
    t = hp.build_tables(runs, details)
    tv.embed_rtl(t)
    for name, rows in t.items():
        for row in rows:
            for key, value in row.items():
                if isinstance(value, str):
                    assert "None" not in value and "null" not in value, (name, key, value)


def test_event_severity_icons_do_not_reuse_verdict_arrows(tables):
    # ▲/▼ mean "budget extended" / "quality lowered" in the legend; severities use ✖ ⚠ ●
    icons = {e["severity_icon"] for e in tables["events"]}
    assert icons <= {"✖", "⚠", "●"}
    assert "⚠" in icons
