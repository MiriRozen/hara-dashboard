import json
from pathlib import Path

import pytest

import hara_prep as hp

DATA = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def loaded():
    return hp.load(DATA)


@pytest.fixture(scope="module")
def runs_by_id(loaded):
    runs, details = loaded
    return {r["run_id"]: r for r in hp.build_runs_table(runs, details)}


# ---------------------------------------------------------------- money


def test_usd_to_micro_is_exact():
    assert hp.usd_to_micro("0.712900") == 712_900
    assert hp.usd_to_micro("0.057860") == 57_860
    assert hp.usd_to_micro(None) is None


def test_usd_to_micro_rejects_sub_micro_precision():
    with pytest.raises(ValueError):
        hp.usd_to_micro("0.0000001")


def test_float_sum_would_drift_but_micro_sum_does_not():
    values = ["0.100000", "0.200000"]
    assert sum(float(v) for v in values) != 0.3  # the reason for the rule
    assert sum(hp.usd_to_micro(v) for v in values) == 300_000


def test_fmt_usd_single_format():
    assert hp.fmt_usd(712_900) == "$0.7129"
    assert hp.fmt_usd(87_430) == "$0.0874"
    assert hp.fmt_usd(87_450) == "$0.0875"  # half-up, not banker's rounding
    assert hp.fmt_usd(2_418_700) == "$2.4187"
    assert hp.fmt_usd(258_108, 6) == "$0.258108"
    assert hp.fmt_usd(-12_360) == "-$0.0124"
    assert hp.fmt_usd(None) == "—"


def test_pct_is_not_capped():
    assert hp.pct(258_108, 57_860) == 446
    assert hp.pct(712_900, 950_000) == 75
    assert hp.pct(712_900, 350_000) == 204
    assert hp.pct(1, 0) is None


def test_duration_labels():
    assert hp.fmt_duration(7) == "7 שנ׳"
    assert hp.fmt_duration(1046) == "17 דק׳ 26 שנ׳"
    assert hp.fmt_duration(3139) == "52 דק׳ 19 שנ׳"
    assert hp.fmt_duration(3600) == "1 שע׳ 0 דק׳"
    assert hp.fmt_duration(None) == "טרם הסתיימה"


def test_local_time_is_israel_summer_time():
    ts = hp.parse_ts("2026-08-18T11:02:18Z")
    assert hp.local_str(ts) == "18.08.2026 14:02"


# ---------------------------------------------------------------- verdicts: one test per edge case in the data


def test_all_13_runs_present(runs_by_id):
    assert len(runs_by_id) == 13


def test_extended_run_is_not_plain_success(runs_by_id):
    r = runs_by_id["run-2c91e7"]
    assert r["verdict"] == "extended"
    assert r["tone"] == "warning"
    assert r["pct_of_approved"] == 75
    assert r["pct_of_initial"] == 204
    assert "מנהל המערכת" in r["attention_reasons"]


def test_downgraded_run_is_flagged_in_list(runs_by_id):
    r = runs_by_id["run-77de40"]
    assert r["verdict"] == "downgraded"
    assert r["downgrade_count"] == 2
    assert "חיפושים 4←2" in r["attention_reasons"]


def test_overrun_shows_446_percent(runs_by_id):
    r = runs_by_id["run-b41055"]
    assert r["verdict"] == "overrun"
    assert r["needs_attention"] == 1
    assert r["pct_label"] == "446%"
    assert r["remaining_micro"] < 0


def test_unknown_cost_is_a_lower_bound(runs_by_id):
    r = runs_by_id["run-9e21d4"]
    assert r["verdict"] == "cost_unknown"
    assert r["spent_label"] == "לפחות $0.2148"
    assert r["open_reservation_micro"] == 260_000
    assert "spent_max_micro" not in r
    assert r["pct_label"].startswith("לפחות")
    # a reservation is an estimate, not a maximum: never "between X and Y" / "up to"
    assert "עלות לא סופית: $0.2600 שוריינו ולא סוכמו — לא ידוע אם חויבנו (והעלות עשויה להיות גבוהה יותר)" \
        in r["attention_reasons"]
    assert "בין $" not in r["attention_reasons"] and "עד $" not in r["attention_reasons"]


def test_running_run_has_no_end(runs_by_id):
    r = runs_by_id["run-5d02b8"]
    assert r["verdict"] == "running"
    assert r["ended_label"] == "טרם הסתיימה"
    assert r["duration_label"] == "טרם הסתיימה"
    assert r["outcome_he"] == "טרם נקבעה"
    assert "עד כה" in r["pct_label"]


def test_partial_run_budget_exhausted(runs_by_id):
    r = runs_by_id["run-6b8823"]
    assert r["verdict"] == "partial"
    assert r["verdict_he"] == "חלקית — התקציב מוצה"
    assert "בקשה להרחבת תקציב לא נענתה (פג הזמן)" in r["attention_reasons"]
    assert "סוכן אחד לא הופעל" in r["attention_reasons"]


def test_cost_gap_between_run_and_agents_is_surfaced(runs_by_id):
    r = runs_by_id["run-48ba13"]
    assert r["cost_gap_micro"] == 41_200 - 28_840
    assert "פער לא מוסבר" in r["attention_reasons"]


def test_zero_cost_failure(runs_by_id):
    r = runs_by_id["run-a1f709"]
    assert r["verdict"] == "failed"
    assert r["spent_micro"] == 0
    assert "provider timeout" in r["attention_reasons"]


def test_clean_success(runs_by_id):
    r = runs_by_id["run-8f3a1c"]
    assert r["verdict"] == "succeeded"
    assert r["attention_reasons"] == ""


def test_summary_totals_are_exact(runs_by_id):
    total = sum(r["spent_micro"] for r in runs_by_id.values())
    assert total == sum(hp.usd_to_micro(r["spent_usd"]) for r in hp.load(DATA)[0])
    assert total == 6_071_538
    assert hp.fmt_usd(total) == "$6.0715"


def test_needs_attention_set(runs_by_id):
    flagged = {k for k, r in runs_by_id.items() if r["needs_attention"]}
    assert flagged == {"run-9e21d4", "run-b41055", "run-48ba13", "run-a1f709", "run-6b8823"}


# ---------------------------------------------------------------- detail tables


def test_node_costs_sum_to_run_cost_where_consistent(loaded):
    runs, details = loaded
    nodes = hp.build_nodes_table(runs, details)
    by_run: dict[str, int] = {}
    for n in nodes:
        by_run[n["run_id"]] = by_run.get(n["run_id"], 0) + n["cost_micro"]
    assert by_run["run-2c91e7"] == 712_900
    assert by_run["run-c33471"] == 2_418_700


def test_turns_of_same_call_are_summed_not_duplicated(loaded):
    runs, details = loaded
    nodes = {(n["run_id"], n["node_id"]): n for n in hp.build_nodes_table(runs, details)}
    n1 = nodes[("run-2c91e7", "n1")]
    assert n1["op_count"] == 2
    assert n1["input_tokens"] == 480 + 6310
    assert n1["web_search_count"] == 9


def test_unsettled_operation_has_no_usage(loaded):
    runs, details = loaded
    ops = [o for o in hp.build_operations_table(runs, details) if o["run_id"] == "run-9e21d4"]
    unsettled = [o for o in ops if not o["settled"]]
    assert len(unsettled) == 1
    assert unsettled[0]["actual_label"] == "לא ידוע"
    assert unsettled[0]["input_tokens"] == ""


def test_node_without_operations_is_marked(loaded):
    runs, details = loaded
    nodes = {(n["run_id"], n["node_id"]): n for n in hp.build_nodes_table(runs, details)}
    assert "נתוני שימוש חסרים" in nodes[("run-11ab02", "n2")]["usage_note"]


def test_budget_segments_single_step_spans_whole_run(loaded):
    runs, details = loaded
    steps = [b for b in hp.build_budget_table(runs, details) if b["run_id"] == "run-8f3a1c"]
    assert len(steps) == 1
    assert steps[0]["to_local"] != ""


def test_budget_segments_extension(loaded):
    runs, details = loaded
    steps = [b for b in hp.build_budget_table(runs, details) if b["run_id"] == "run-2c91e7"]
    assert [s["ceiling_micro"] for s in steps] == [350_000, 950_000]
    assert steps[0]["to_local"] == steps[1]["from_local"]


def test_running_budget_segment_is_open(loaded):
    runs, details = loaded
    steps = [b for b in hp.build_budget_table(runs, details) if b["run_id"] == "run-5d02b8"]
    assert steps[0]["to_label"] == "עדיין בתוקף"


def test_every_event_type_has_hebrew_and_description(loaded):
    runs, details = loaded
    for e in hp.build_events_table(runs, details):
        assert e["type_he"] != e["type"], e["type"]
        assert not e["description"].startswith("{"), e


# ---------------------------------------------------------------- synthetic edge cases (shared verdict spec v2)

T0, T1 = "2026-08-01T10:00:00Z", "2026-08-01T10:10:00Z"


def mk_run(**kw):
    r = {"run_id": "run-syn", "title": "ריצה סינתטית", "requested_by": "בודק", "status": "completed",
         "outcome": "succeeded", "initial_budget_usd": "1.000000", "approved_budget_usd": "1.000000",
         "spent_usd": "0.100000", "started_at": T0, "ended_at": T1, "agent_count": 1, "cost_is_complete": True}
    r.update(kw)
    return r


def mk_node(**kw):
    n = {"node_id": "n1", "agent_name": "סוכן בדיקה", "role": "research", "tier": "worker",
         "model": "claude-sonnet-4-6", "status": "succeeded", "cost_usd": "0.100000", "started_at": T0,
         "ended_at": T1, "visible_summary": None}
    n.update(kw)
    return n


def mk_usage(**kw):
    u = {"input_tokens": 100, "output_tokens": 100, "cache_read_tokens": 0, "cache_creation_tokens": 0,
         "web_search_count": 0, "max_tokens_cap": 2000, "max_searches_cap": 0}
    u.update(kw)
    return u


def mk_op(**kw):
    o = {"operation_id": "01SYN:t0", "node_id": "n1", "estimated_usd": "0.100000", "actual_usd": "0.100000",
         "settled": True, "usage": mk_usage()}
    o.update(kw)
    return o


def mk_ev(type_, at="2026-08-01T10:05:00Z", **payload):
    return {"at": at, "type": type_, "payload": payload}


def mk_detail(nodes=None, operations=None, events=None, budget_timeline=None):
    return {
        "nodes": [mk_node()] if nodes is None else nodes,
        "operations": [mk_op()] if operations is None else operations,
        "events": events or [],
        "budget_timeline": [{"at": T0, "ceiling_usd": "1.000000", "reason": "initial_approval"}]
        if budget_timeline is None else budget_timeline,
    }


def one_row(run, detail=None):
    return hp.build_runs_table([run], {run["run_id"]: mk_detail() if detail is None else detail})[0]


UNSETTLED = mk_detail(
    nodes=[mk_node(), mk_node(node_id="n2", cost_usd="0.000000", status="failed")],
    operations=[mk_op(), mk_op(operation_id="01SYN2:t0", node_id="n2", estimated_usd="0.070000",
                               actual_usd=None, settled=False, usage=None)],
)


def test_synthetic_baseline_is_a_clean_success():
    r = one_row(mk_run())
    assert (r["verdict"], r["tone"], r["attention_reasons"]) == ("succeeded", "ok", "")


def test_completed_with_partial_outcome_is_partial():
    r = one_row(mk_run(outcome="partial"))
    assert (r["verdict"], r["tone"], r["verdict_label"]) == ("partial", "critical", "◑ הושלמה חלקית")


def test_completed_with_failed_outcome_is_failed():
    r = one_row(mk_run(outcome="failed"))
    assert (r["verdict"], r["tone"]) == ("failed", "critical")
    assert r["attention_reasons"] == "הריצה נכשלה"


def test_pending_run_is_pending():
    r = one_row(
        mk_run(status="pending", outcome=None, spent_usd="0.000000", started_at=None, ended_at=None),
        mk_detail(nodes=[mk_node(status="pending", cost_usd="0.000000", model=None, started_at=None, ended_at=None)],
                  operations=[], budget_timeline=[]),
    )
    assert (r["verdict"], r["tone"], r["verdict_label"]) == ("pending", "neutral", "○ ממתינה — טרם התחילה")


def test_running_run_over_its_ceiling_is_overrun():
    r = one_row(mk_run(status="running", outcome=None, ended_at=None,
                       initial_budget_usd="0.050000", approved_budget_usd="0.050000"))
    assert (r["verdict"], r["tone"]) == ("overrun", "critical")
    assert "ההוצאה $0.1000 עברה את התקרה $0.0500 (200%)" in r["attention_reasons"]


def test_cost_gap_alone_is_its_own_critical_verdict():
    r = one_row(mk_run(spent_usd="0.150000"))  # the only agent cost 0.10
    assert (r["verdict"], r["tone"], r["verdict_label"]) == ("cost_gap", "critical", "≠ פער לא מוסבר בעלות")


def test_tiny_cost_gap_is_printed_with_six_decimals():
    r = one_row(mk_run(spent_usd="0.100040"))
    assert r["verdict"] == "cost_gap"
    assert "פער לא מוסבר של $0.000040 בין" in r["attention_reasons"]


def test_denied_approval_alone_needs_review():
    r = one_row(mk_run(), mk_detail(events=[mk_ev("approval_denied", decision="denied", reason="rejected")]))
    assert (r["verdict"], r["tone"], r["verdict_label"]) == ("needs_review", "critical", "! דורש בירור")
    assert r["attention_reasons"] == "בקשה להרחבת תקציב נדחתה"


def test_completed_without_outcome_is_not_a_success():
    r = one_row(mk_run(outcome=None))
    assert (r["verdict"], r["tone"], r["verdict_label"]) == ("no_outcome", "warning", "? הושלמה, תוצאה לא ידועה")


def test_unsettled_operation_without_event_makes_cost_unknown():
    r = one_row(mk_run(), UNSETTLED)
    assert (r["verdict"], r["tone"], r["cost_is_complete"]) == ("cost_unknown", "critical", 0)
    assert r["open_reservation_micro"] == 70_000  # the estimate, since no event reports the reservation
    assert r["spent_label"] == "לפחות $0.1000"
    assert "עלות לא סופית: $0.0700 שוריינו ולא סוכמו" in r["attention_reasons"]


def test_unsettled_operation_in_a_running_run_is_in_flight_not_unknown():
    r = one_row(mk_run(status="running", outcome=None, ended_at=None), UNSETTLED)
    assert (r["verdict"], r["tone"], r["cost_is_complete"]) == ("running", "neutral", 1)


def test_cost_unknown_without_open_reservation_is_a_lower_bound_only():
    r = one_row(mk_run(cost_is_complete=False))
    assert r["open_reservation_micro"] == 0
    assert r["attention_reasons"] == "עלות לא סופית: $0.1000 הוא חסם תחתון בלבד"


def test_running_run_with_a_critical_reason_is_critical():
    r = one_row(mk_run(status="running", outcome=None, ended_at=None),
                mk_detail(events=[mk_ev("approval_denied", decision="denied", reason="timeout_no_response")]))
    assert (r["verdict"], r["tone"], r["needs_attention"]) == ("running", "critical", 1)


def test_reasons_carry_their_own_tone(runs_by_id):
    assert runs_by_id["run-a1f709"]["attention_tones"] == "critical • info"
    assert runs_by_id["run-a1f709"]["reasons_tone"] == "critical"
    assert runs_by_id["run-2c91e7"]["reasons_tone"] == "warning"
    assert runs_by_id["run-11ab02"]["reasons_tone"] == "muted"  # info only
    assert runs_by_id["run-8f3a1c"]["reasons_tone"] == "ok"


def test_failure_reason_is_ltr_isolated_and_timeout_mismatch_is_noted(runs_by_id):
    r = runs_by_id["run-a1f709"]
    assert "הריצה נכשלה: " + hp.ltr("provider timeout after 600s") in r["attention_reasons"]
    assert "שגיאת timeout של 600 שנ׳ אינה תואמת משך ריצה של 7 שנ׳ — אי-התאמה בנתונים" in r["attention_reasons"]


def test_zero_denominators_never_print_none():
    r = one_row(mk_run(initial_budget_usd="0.000000", approved_budget_usd="0.000000"))
    assert r["verdict"] == "overrun"
    assert "None" not in r["attention_reasons"] and "None" not in r["pct_label"]
    assert "(—)" in r["attention_reasons"]
    r = one_row(mk_run(initial_budget_usd="0.000000"))
    assert r["verdict"] == "extended"
    assert "ההוצאה היא — מהתקציב המקורי" in r["attention_reasons"]


def test_event_offset_keeps_its_sign_next_to_the_number(loaded):
    runs, details = loaded
    first = [e for e in hp.build_events_table(runs, details) if e["run_id"] == "run-2c91e7"][0]
    assert first["offset_label"] == hp.ltr("+6") + " דק׳ 23 שנ׳"
    run = mk_run()
    early = hp.build_events_table([run], {run["run_id"]: mk_detail(
        events=[mk_ev("llm_call", at="2026-08-01T09:59:30Z", turns=1)])})[0]
    assert early["offset_label"] == hp.ltr("-30") + " שנ׳"


def test_events_after_run_end_are_tagged(loaded):
    runs, details = loaded
    ev = {e["seq"]: e for e in hp.build_events_table(runs, details) if e["run_id"] == "run-6b8823"}
    assert ev[2]["after_end"] == 0  # exactly at the end
    assert ev[3]["after_end"] == 1 and ev[4]["after_end"] == 1


def test_budget_threshold_events_show_the_actual_percent(loaded):
    runs, details = loaded
    ev = {(e["run_id"], e["seq"]): e for e in hp.build_events_table(runs, details)}
    assert ev[("run-6b8823", 1)]["description"] == "הוצאו $0.3720 מתוך תקרה של $0.4000 (93%)"
    assert ev[("run-2c91e7", 1)]["description"] == "הוצאו $0.2840 מתוך תקרה של $0.3500 (81%)"


def test_llm_call_event_says_the_turns_come_from_the_event(loaded):
    runs, details = loaded
    ev = [e for e in hp.build_events_table(runs, details) if e["run_id"] == "run-8f3a1c" and e["type"] == "llm_call"]
    assert ev[0]["description"] == "קריאות מודל הושלמו (3 תורות לפי האירוע)"


def test_pending_agent_in_a_running_run_is_waiting_not_skipped(loaded):
    runs, details = loaded
    nodes = {(n["run_id"], n["node_id"]): n for n in hp.build_nodes_table(runs, details)}
    assert nodes[("run-5d02b8", "n3")]["status_he"] == "ממתין"
    assert nodes[("run-48ba13", "n2")]["status_he"] == "לא הופעל"
    n2 = nodes[("run-5d02b8", "n2")]
    assert (n2["usage_note"], n2["usage_note_tone"]) == ("טרם בוצעו קריאות", "neutral")


def test_agent_whose_call_failed_without_a_record_is_critical(loaded):
    runs, details = loaded
    nodes = {(n["run_id"], n["node_id"]): n for n in hp.build_nodes_table(runs, details)}
    n = nodes[("run-a1f709", "n1")]
    assert (n["usage_note"], n["usage_note_tone"]) == ("קריאת מודל נכשלה — אין רשומת קריאה ונתוני שימוש", "critical")


def test_agent_with_an_unsettled_reservation(loaded):
    runs, details = loaded
    nodes = {(n["run_id"], n["node_id"]): n for n in hp.build_nodes_table(runs, details)}
    n = nodes[("run-9e21d4", "n2")]
    assert (n["usage_note"], n["usage_note_tone"]) == ("קריאה אחת לא סוכמה — עלות ושימוש לא ידועים", "critical")
    assert n["cost_display"] == "לא ידוע (שוריינו $0.2600)"
    assert n["share_label"] == ""
    assert n["bar_label"].startswith("אנליסט שכר: לא ידוע (שוריינו $0.2600)")
    assert nodes[("run-9e21d4", "n1")]["share_label"] == "100% מהעלות הידועה"
    assert nodes[("run-2c91e7", "n1")]["share_label"] == "56%"


def test_unsettled_note_counts_calls():
    ops = [mk_op(operation_id=f"01SYN:t{i}", estimated_usd="0.050000", actual_usd=None, settled=False, usage=None)
           for i in range(2)]
    run = mk_run()
    n = hp.build_nodes_table([run], {run["run_id"]: mk_detail(operations=ops)})[0]
    assert n["usage_note"] == "2 קריאות לא סוכמו — עלות ושימוש לא ידועים"
    assert n["cost_display"] == "לא ידוע (שוריינו $0.1000)"


def test_visible_summary_keeps_the_number_after_a_semicolon_in_place(loaded):
    runs, details = loaded
    nodes = {(n["run_id"], n["node_id"]): n for n in hp.build_nodes_table(runs, details)}
    assert nodes[("run-2c91e7", "n1")]["visible_summary"] == "נסקרו GDPR ו-AI Act; ‏22 מקורות"


def test_long_agent_names_are_truncated_in_bar_labels(loaded):
    runs, details = loaded
    nodes = {(n["run_id"], n["node_id"]): n for n in hp.build_nodes_table(runs, details)}
    assert nodes[("run-c33471", "n1")]["bar_label"].startswith("רכזת מחקר ראשית לתחומ…: $0.8124")
    assert nodes[("run-c33471", "n2")]["bar_label"].startswith("חוקר שוק: ")


def test_zero_estimate_has_no_delta_percent():
    run = mk_run()
    o = hp.build_operations_table([run], {run["run_id"]: mk_detail(operations=[mk_op(estimated_usd="0.000000")])})[0]
    assert o["delta_micro"] == 100_000
    assert o["delta_pct"] == ""


def test_calls_over_their_caps_are_flagged(loaded):
    runs, details = loaded
    ops = {o["operation_id"]: o for o in hp.build_operations_table(runs, details)}
    assert (ops["01H2C91A:t0"]["output_over_cap"], ops["01H2C91A:t0"]["searches_over_cap"]) == (1, 0)
    assert (ops["01H8F3B:t0"]["output_over_cap"], ops["01H8F3B:t0"]["searches_over_cap"]) == (0, 0)
    assert ops["01H9E21B:t0"]["output_over_cap"] == 0  # unsettled: no usage, nothing to compare


def test_write_csv_empty_table_keeps_its_header(tmp_path):
    p = tmp_path / "x.csv"
    hp.write_csv(p, [], ["a", "b"])
    assert p.read_text(encoding="utf-8").splitlines() == ["a,b"]


def test_build_all_writes_every_table_for_a_run_without_detail(tmp_path):
    data = tmp_path / "data"
    (data / "runs").mkdir(parents=True)
    run = mk_run(status="pending", outcome=None, spent_usd="0.000000", ended_at=None)
    (data / "runs.json").write_text(json.dumps({"runs": [run]}, ensure_ascii=False), encoding="utf-8")
    counts = hp.build_all(data, tmp_path / "out")
    assert counts["nodes"] == 0 and counts["events"] == 0 and counts["operations"] == 0 and counts["budget"] == 0
    for name in counts:
        header = (tmp_path / "out" / f"{name}.csv").read_text(encoding="utf-8").splitlines()[0]
        assert header.count(",") > 2, name
    nodes_header = (tmp_path / "out" / "nodes.csv").read_text(encoding="utf-8").splitlines()[0]
    assert nodes_header.startswith("run_id,node_id,")
