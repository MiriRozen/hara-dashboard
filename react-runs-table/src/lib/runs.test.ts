import { runs, signals } from "./fixtures";
import { compare, formatDate, formatDuration, REASON_ICON, signalsFromDetail, toRunRow, VERDICT } from "./runs";
import type { RunDetail, RunSummary } from "./types";

const row = (id: string) => {
  const r = runs.find((x) => x.run_id === id);
  if (!r) throw new Error(id);
  return toRunRow(r, signals[id]);
};

describe("verdicts on the real fixtures", () => {
  it("covers all 13 runs", () => {
    expect(runs).toHaveLength(13);
  });

  it("mid-run extension is not a plain green success", () => {
    const r = row("run-2c91e7");
    expect(r.verdict).toBe("extended");
    expect(r.tone).toBe("warning");
    expect(r.pctOfApproved).toBe(75);
    expect(r.pctOfInitial).toBe(204);
    expect(r.reasons.map((x) => x.text).join()).toContain("מנהל המערכת");
  });

  it("quality downgrade is visible in the list", () => {
    const r = row("run-77de40");
    expect(r.verdict).toBe("downgraded");
    expect(r.reasons[0]?.text).toContain("חיפושים 4←2");
  });

  it("token counts in the downgrade reason use thousands separators, like the Tableau text", () => {
    expect(row("run-77de40").reasons[0]?.text).toContain("כותב הדוח: אורך פלט 3,000←1,200 טוקנים");
  });

  it("without detail signals a downgraded run looks like success — the reason signals exist", () => {
    const r = runs.find((x) => x.run_id === "run-77de40")!;
    expect(toRunRow(r).verdict).toBe("succeeded");
  });

  it("overrun keeps 446%", () => {
    const r = row("run-b41055");
    expect(r.verdict).toBe("overrun");
    expect(r.pctOfApproved).toBe(446);
  });

  it("unknown cost is a lower bound plus an open reservation — never an upper bound", () => {
    const r = row("run-9e21d4");
    expect(r.verdict).toBe("cost_unknown");
    expect(r.costIsFinal).toBe(false);
    expect(r.spent).toBe(214_800n);
    expect(r.openReservation).toBe(260_000n);
    expect(r.reasons[0]).toEqual({
      tone: "critical",
      text: "עלות לא סופית: $0.2600 שוריינו ולא סוכמו — לא ידוע אם חויבנו (והעלות עשויה להיות גבוהה יותר)",
    });
    expect(r.reasons.map((x) => x.text).join()).not.toMatch(/עד|בין/);
  });

  it("running run has no end and no outcome", () => {
    const r = row("run-5d02b8");
    expect(r.verdict).toBe("running");
    expect(r.endedAt).toBeNull();
    expect(formatDuration(r.durationSec)).toBe("טרם הסתיימה");
  });

  it("partial run with a denied approval needs attention", () => {
    const r = row("run-6b8823");
    expect(r.verdict).toBe("partial");
    expect(r.tone).toBe("critical");
  });

  it("clean success has no reasons", () => {
    expect(row("run-8f3a1c").reasons).toEqual([]);
  });

  it("partial run says why: denied-by-timeout and one agent not run", () => {
    const r = row("run-6b8823");
    expect(r.verdictLabel).toBe("חלקית — התקציב מוצה");
    expect(r.reasons).toEqual([
      { tone: "critical", text: "בקשה להרחבת תקציב לא נענתה (פג הזמן)" },
      { tone: "critical", text: "התקציב מוצה — סוכן אחד לא הופעל" },
    ]);
  });

  it("overrun reason reads spent, ceiling and percent", () => {
    expect(row("run-b41055").reasons).toEqual([
      { tone: "critical", text: "ההוצאה $0.2581 עברה את התקרה $0.0579 (446%)" },
    ]);
  });

  it("extension reason names the approver and the original budget", () => {
    expect(row("run-2c91e7").reasons).toEqual([
      {
        tone: "warning",
        text: "התקרה הורחבה באמצע הריצה מ-$0.3500 ל-$0.9500 (אישר: מנהל המערכת); ההוצאה היא 204% מהתקציב המקורי",
      },
    ]);
  });

  it("failed run with a reported cost that the agents do not add up to shows the gap", () => {
    const r = row("run-48ba13");
    expect(r.verdict).toBe("failed");
    expect(r.reasons).toEqual([
      { tone: "critical", text: "פער לא מוסבר של $0.0124 בין העלות המדווחת לסכום עלויות הסוכנים" },
      {
        tone: "critical",
        text: "הריצה נכשלה: invalid_request: context length exceeded",
        isolate: "invalid_request: context length exceeded",
      },
    ]);
  });

  it("a 600s timeout on a 7-second run is flagged as a data mismatch", () => {
    const r = row("run-a1f709");
    expect(r.verdict).toBe("failed");
    expect(r.reasons).toEqual([
      { tone: "critical", text: "הריצה נכשלה: provider timeout after 600s", isolate: "provider timeout after 600s" },
      { tone: "info", text: "שגיאת timeout של 600 שנ׳ אינה תואמת משך ריצה של 7 שנ׳ — אי-התאמה בנתונים" },
    ]);
  });

  it("agents with cost but no call records are an info note, not a verdict change", () => {
    for (const id of ["run-11ab02", "run-24cd51", "run-39ef77"]) {
      const r = row(id);
      expect(r.verdict).toBe("succeeded");
      expect(r.tone).toBe("ok");
      expect(r.reasons).toEqual([{ tone: "info", text: "לחלק מהסוכנים אין רשומות קריאה — נתוני שימוש חסרים" }]);
    }
  });

  it("process death keeps the failure reason next to the unknown cost", () => {
    expect(row("run-9e21d4").reasons[1]).toEqual({
      tone: "critical",
      text: "הריצה נכשלה: התהליך מת באמצע קריאה למודל",
      isolate: "התהליך מת באמצע קריאה למודל",
    });
  });

  it("never prints null/undefined/NaN in any reason", () => {
    for (const r of runs) {
      for (const reason of row(r.run_id).reasons) expect(reason.text).not.toMatch(/null|undefined|NaN/);
    }
  });
});

// ---------------------------------------------------------------- synthetic runs for every branch of the spec

const BASE: RunSummary = {
  run_id: "run-test",
  title: "ריצת בדיקה",
  requested_by: "בודק",
  status: "completed",
  outcome: "succeeded",
  initial_budget_usd: "1.000000",
  approved_budget_usd: "1.000000",
  spent_usd: "0.500000",
  started_at: "2026-09-01T10:00:00Z",
  ended_at: "2026-09-01T10:10:00Z",
  agent_count: 1,
  cost_is_complete: true,
};

function make(over: Partial<RunSummary> = {}, detail: Partial<Pick<RunDetail, "nodes" | "operations" | "events">> = {}) {
  const run = { ...BASE, ...over };
  const { agent_count: _unused, ...rest } = run;
  return toRunRow(run, signalsFromDetail({ ...rest, nodes: [], operations: [], events: [], ...detail }));
}

const node = (node_id: string, cost_usd: string) => ({ node_id, agent_name: node_id, cost_usd });
const op = (operation_id: string, estimated_usd: string, settled: boolean, actual_usd: string | null = null) => ({
  operation_id,
  node_id: "n1",
  estimated_usd,
  actual_usd,
  settled,
});

describe("verdict spec v2", () => {
  it("VERDICT table matches the shared spec exactly", () => {
    expect(VERDICT).toEqual({
      pending: { label: "ממתינה — טרם התחילה", tone: "neutral", icon: "○" },
      cost_unknown: { label: "עלות לא ידועה — דורש התאמה", tone: "critical", icon: "?" },
      overrun: { label: "חריגה מהתקרה", tone: "critical", icon: "!" },
      running: { label: "בריצה — טרם הסתיימה", tone: "neutral", icon: "◔" },
      failed: { label: "נכשלה", tone: "critical", icon: "✖" },
      partial: { label: "הושלמה חלקית", tone: "critical", icon: "◑" },
      cost_gap: { label: "פער לא מוסבר בעלות", tone: "critical", icon: "≠" },
      needs_review: { label: "דורש בירור", tone: "critical", icon: "!" },
      no_outcome: { label: "הושלמה, תוצאה לא ידועה", tone: "warning", icon: "?" },
      downgraded: { label: "הצליחה, באיכות מופחתת", tone: "warning", icon: "▼" },
      extended: { label: "הצליחה, אחרי הרחבת תקציב", tone: "warning", icon: "▲" },
      succeeded: { label: "הצליחה", tone: "ok", icon: "✔" },
    });
    expect(REASON_ICON).toEqual({ critical: "✖", warning: "⚠", info: "ⓘ" });
  });

  it("pending run is pending, not a success", () => {
    const r = make({ status: "pending", outcome: null, spent_usd: "0.000000", ended_at: null });
    expect(r.verdict).toBe("pending");
    expect(r.tone).toBe("neutral");
  });

  it("completed + outcome partial is partial (critical), labelled without budget exhaustion", () => {
    const r = make({ outcome: "partial" });
    expect(r.verdict).toBe("partial");
    expect(r.verdictLabel).toBe("הושלמה חלקית");
    expect(r.tone).toBe("critical");
  });

  it("completed + outcome failed is failed", () => {
    const r = make({ outcome: "failed" });
    expect(r.verdict).toBe("failed");
    expect(r.tone).toBe("critical");
    expect(r.reasons).toEqual([{ tone: "critical", text: "הריצה נכשלה" }]);
  });

  it("completed with no outcome is not a success", () => {
    const r = make({ outcome: null });
    expect(r.verdict).toBe("no_outcome");
    expect(r.verdictLabel).toBe("הושלמה, תוצאה לא ידועה");
    expect(r.tone).toBe("warning");
  });

  it("running run that already overran is an overrun (critical), not 'running'", () => {
    const r = make({ status: "running", outcome: null, ended_at: null, spent_usd: "1.200000" });
    expect(r.verdict).toBe("overrun");
    expect(r.tone).toBe("critical");
  });

  it("running run with a critical reason keeps its verdict but turns critical", () => {
    const r = make({ status: "running", outcome: null, ended_at: null }, { nodes: [node("n1", "0.400000")] });
    expect(r.verdict).toBe("running");
    expect(r.tone).toBe("critical");
  });

  it("budget_overrun_detected event is an overrun even when spent <= approved", () => {
    const r = make({}, { events: [{ at: BASE.started_at, type: "budget_overrun_detected", payload: {} }] });
    expect(r.verdict).toBe("overrun");
    expect(r.tone).toBe("critical");
  });

  it("reported cost != sum of agent costs is a cost_gap", () => {
    const r = make({}, { nodes: [node("n1", "0.300000"), node("n2", "0.100000")] });
    expect(r.verdict).toBe("cost_gap");
    expect(r.tone).toBe("critical");
    expect(r.reasons[0]).toEqual({
      tone: "critical",
      text: "פער לא מוסבר של $0.1000 בין העלות המדווחת לסכום עלויות הסוכנים",
    });
  });

  it("a gap too small for 4 decimals is printed with 6", () => {
    const r = make({}, { nodes: [node("n1", "0.499960")] });
    expect(r.reasons[0]?.text).toBe("פער לא מוסבר של $0.000040 בין העלות המדווחת לסכום עלויות הסוכנים");
  });

  it("no nodes in the detail means no gap check", () => {
    expect(make().verdict).toBe("succeeded");
  });

  it("denied approval (not a timeout) needs review", () => {
    const r = make({}, { events: [{ at: BASE.started_at, type: "approval_denied", payload: { reason: "rejected" } }] });
    expect(r.verdict).toBe("needs_review");
    expect(r.tone).toBe("critical");
    expect(r.reasons).toEqual([{ tone: "critical", text: "בקשה להרחבת תקציב נדחתה" }]);
  });

  it("unsettled operation without an unresolved event still makes the cost unknown", () => {
    const r = make({}, { operations: [op("OP1:t0", "0.120000", false)] });
    expect(r.verdict).toBe("cost_unknown");
    expect(r.costIsFinal).toBe(false);
    expect(r.openReservation).toBe(120_000n);
    expect(r.reasons[0]?.text).toBe(
      "עלות לא סופית: $0.1200 שוריינו ולא סוכמו — לא ידוע אם חויבנו (והעלות עשויה להיות גבוהה יותר)",
    );
  });

  it("an unsettled operation with a matching unresolved event is counted once", () => {
    const r = make(
      {},
      {
        operations: [op("OP1:t0", "0.120000", false)],
        events: [{ at: BASE.started_at, type: "budget_reservation_unresolved", payload: { operation_id: "OP1:t0", reserved_usd: "0.150000" } }],
      },
    );
    expect(r.openReservation).toBe(150_000n);
  });

  it("an in-flight operation of a running run is not an unknown cost", () => {
    const r = make({ status: "running", outcome: null, ended_at: null }, { operations: [op("OP1:t0", "0.120000", false)] });
    expect(r.verdict).toBe("running");
    expect(r.costIsFinal).toBe(true);
  });

  it("cost_is_complete=false with nothing open says spent is a lower bound", () => {
    const r = make({ cost_is_complete: false });
    expect(r.verdict).toBe("cost_unknown");
    expect(r.reasons[0]?.text).toBe("עלות לא סופית: $0.5000 הוא חסם תחתון בלבד");
  });

  it("budget exhausted with several agents left", () => {
    const r = make({}, { events: [{ at: BASE.started_at, type: "budget_exhausted", payload: { remaining_nodes: 3 } }] });
    expect(r.verdict).toBe("partial");
    expect(r.verdictLabel).toBe("חלקית — התקציב מוצה");
    expect(r.reasons).toEqual([{ tone: "critical", text: "התקציב מוצה — 3 סוכנים לא הופעלו" }]);
  });

  it("a zero denominator prints '—', never null", () => {
    const extended = make({ initial_budget_usd: "0.000000" });
    expect(extended.verdict).toBe("extended");
    expect(extended.reasons[0]?.text).toBe(
      "התקרה הורחבה באמצע הריצה מ-$0.0000 ל-$1.0000; ההוצאה היא — מהתקציב המקורי",
    );
    const overrun = make({ initial_budget_usd: "0.000000", approved_budget_usd: "0.000000" });
    expect(overrun.reasons[0]?.text).toBe("ההוצאה $0.5000 עברה את התקרה $0.0000 (—)");
    for (const r of [extended, overrun]) {
      for (const reason of r.reasons) expect(reason.text).not.toMatch(/null|undefined|NaN/);
    }
  });

  it("reasons are ordered critical, then warning, then info", () => {
    const r = make(
      { approved_budget_usd: "2.000000", status: "failed", outcome: "failed" },
      {
        nodes: [node("n1", "0.500000"), node("n2", "0.000000")],
        operations: [],
        events: [
          { at: BASE.started_at, type: "execution_cap_downgraded", payload: { node_id: "n1", from_searches: 4, to_searches: 2 } },
          { at: BASE.started_at, type: "llm_call_failed", payload: { error: "timeout after 9999s" } },
        ],
      },
    );
    expect(r.reasons.map((x) => x.tone)).toEqual(["critical", "warning", "warning", "info", "info"]);
  });
});

describe("default sort: attention first, then newest", () => {
  it("orders the real fixtures by tone, then started_at newest first", () => {
    const ordered = runs.map((r) => row(r.run_id)).sort((a, b) => compare(a, b, "attention"));
    expect(ordered.map((r) => r.id)).toEqual([
      // critical, newest first
      "run-b41055",
      "run-9e21d4",
      "run-a1f709",
      "run-6b8823",
      "run-48ba13",
      // warning
      "run-77de40",
      "run-2c91e7",
      // neutral
      "run-5d02b8",
      // ok
      "run-c33471",
      "run-8f3a1c",
      "run-39ef77",
      "run-24cd51",
      "run-11ab02",
    ]);
    expect(ordered.slice(0, 5).every((r) => r.tone === "critical")).toBe(true);
  });
});

describe("formatting", () => {
  it("shows dates in Israel time", () => {
    expect(formatDate(new Date("2026-08-18T11:02:18Z"))).toMatch(/18\.08\.2026.*14:02/);
  });
  it("formats durations in Hebrew", () => {
    expect(formatDuration(7)).toBe("7 שנ׳");
    expect(formatDuration(1046)).toBe("17 דק׳ 26 שנ׳");
  });
});
