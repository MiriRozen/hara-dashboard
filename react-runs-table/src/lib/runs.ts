import { formatPercent, formatUsd, type Micro, parseUsd, percentOf, toUsdString } from "./money";
import type { RunDetail, RunListSignals, RunStatus, RunSummary } from "./types";

export const STATUS_LABEL: Record<RunStatus, string> = {
  pending: "ממתינה",
  running: "בריצה",
  completed: "הושלמה",
  partial: "הושלמה חלקית",
  failed: "נכשלה",
};

export const OUTCOME_LABEL: Record<string, string> = {
  succeeded: "הצליחה",
  partial: "חלקית",
  failed: "נכשלה",
};

/** critical = a human must look; warning = worth knowing; ok; neutral = still running */
export type Tone = "critical" | "warning" | "ok" | "neutral";

export type Verdict =
  | "pending"
  | "cost_unknown"
  | "overrun"
  | "running"
  | "failed"
  | "partial"
  | "cost_gap"
  | "needs_review"
  | "no_outcome"
  | "downgraded"
  | "extended"
  | "succeeded";

export const VERDICT: Record<Verdict, { label: string; tone: Tone; icon: string }> = {
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
};

const PARTIAL_EXHAUSTED_LABEL = "חלקית — התקציב מוצה";

export const TONE_LABEL: Record<Tone, string> = {
  critical: "דורש בירור",
  warning: "לידיעה",
  ok: "תקין",
  neutral: "בתהליך",
};

export type ReasonTone = "critical" | "warning" | "info";

export const REASON_ICON: Record<ReasonTone, string> = { critical: "✖", warning: "⚠", info: "ⓘ" };

export interface Reason {
  tone: ReasonTone;
  text: string;
  isolate?: string;
}

export interface RunRow {
  id: string;
  title: string;
  requestedBy: string;
  status: RunStatus;
  outcome: RunSummary["outcome"];
  verdict: Verdict;
  verdictLabel: string;
  tone: Tone;
  reasons: Reason[];
  initial: Micro;
  approved: Micro;
  spent: Micro;
  /** reserved and never settled — an estimate, NOT an upper bound: the real charge can be higher */
  openReservation: Micro;
  costIsFinal: boolean;
  isExtended: boolean;
  pctOfApproved: number | null;
  pctOfInitial: number | null;
  startedAt: Date;
  endedAt: Date | null;
  durationSec: number | null;
}

export const EMPTY_SIGNALS: RunListSignals = {
  downgrades: [],
  extensionApprovedBy: null,
  openReservationUsd: null,
  reservationUnresolved: false,
  unsettledOperations: 0,
  overrunDetected: false,
  costGapUsd: null,
  nodesMissingUsage: false,
  budgetExhausted: false,
  nodesNotRun: null,
  approvalDenied: false,
  approvalDeniedReason: null,
  failureReason: null,
};

export function signalsFromDetail(detail: RunDetail): RunListSignals {
  const names = new Map(detail.nodes.map((n) => [n.node_id, n.agent_name]));
  const operations = detail.operations ?? [];
  const s: RunListSignals = { ...EMPTY_SIGNALS, downgrades: [] };
  let open = 0n;
  const unresolvedOps = new Set<string>();
  for (const ev of detail.events) {
    const p = (ev.payload ?? {}) as Record<string, unknown>;
    const who = names.get(String(p.node_id)) ?? String(p.node_id ?? "");
    switch (ev.type) {
      case "execution_cap_downgraded":
        if (typeof p.from_searches === "number") {
          s.downgrades.push(`${who}: חיפושים ${p.from_searches}←${p.to_searches}`);
        } else if (typeof p.from_max_tokens === "number") {
          s.downgrades.push(
            `${who}: אורך פלט ${p.from_max_tokens.toLocaleString("en-US")}←${Number(p.to_max_tokens).toLocaleString("en-US")} טוקנים`,
          );
        } else {
          s.downgrades.push(`${who}: היקף העבודה הוקטן`);
        }
        break;
      case "approval_resolved":
        if (p.decision === "approved" && typeof p.by === "string") s.extensionApprovedBy = p.by;
        break;
      case "budget_reservation_unresolved":
        s.reservationUnresolved = true;
        if (typeof p.reserved_usd === "string") open += parseUsd(p.reserved_usd);
        if (typeof p.operation_id === "string") unresolvedOps.add(p.operation_id);
        break;
      case "budget_overrun_detected":
        s.overrunDetected = true;
        break;
      case "budget_exhausted":
        s.budgetExhausted = true;
        s.nodesNotRun = typeof p.remaining_nodes === "number" ? p.remaining_nodes : null;
        break;
      case "approval_denied":
        s.approvalDenied = true;
        s.approvalDeniedReason = typeof p.reason === "string" ? p.reason : null;
        break;
      case "llm_call_failed":
        s.failureReason ??= typeof p.error === "string" ? p.error : null;
        break;
      case "process_terminated":
        s.failureReason ??= "התהליך מת באמצע קריאה למודל";
        break;
    }
  }
  for (const op of operations) {
    if (op.settled) continue;
    s.unsettledOperations += 1;
    if (!unresolvedOps.has(op.operation_id)) open += parseUsd(op.estimated_usd);
  }
  if (open > 0n) s.openReservationUsd = toUsdString(open);
  if (detail.nodes.length > 0) {
    const nodeSum = detail.nodes.reduce((acc, n) => acc + parseUsd(n.cost_usd), 0n);
    s.costGapUsd = toUsdString(parseUsd(detail.spent_usd) - nodeSum);
  }
  const nodesWithOps = new Set(operations.map((o) => o.node_id));
  s.nodesMissingUsage = detail.nodes.some((n) => parseUsd(n.cost_usd) > 0n && !nodesWithOps.has(n.node_id));
  return s;
}

function pickVerdict(run: RunSummary, s: RunListSignals, overrun: boolean, costFinal: boolean, costGap: Micro): Verdict {
  if (run.status === "pending") return "pending";
  if (!costFinal) return "cost_unknown";
  if (overrun) return "overrun";
  if (run.status === "running") return "running";
  if (run.status === "failed" || run.outcome === "failed") return "failed";
  if (run.status === "partial" || run.outcome === "partial" || s.budgetExhausted) return "partial";
  if (costGap !== 0n) return "cost_gap";
  if (s.approvalDenied) return "needs_review";
  if (run.outcome !== "succeeded") return "no_outcome";
  if (s.downgrades.length > 0) return "downgraded";
  if (parseUsd(run.approved_budget_usd) > parseUsd(run.initial_budget_usd)) return "extended";
  return "succeeded";
}

function formatGap(gap: Micro): string {
  const abs = gap < 0n ? -gap : gap;
  return formatUsd(abs) === "$0.0000" ? formatUsd(abs, 6) : formatUsd(abs);
}

export function toRunRow(run: RunSummary, signals: RunListSignals = EMPTY_SIGNALS): RunRow {
  const initial = parseUsd(run.initial_budget_usd);
  const approved = parseUsd(run.approved_budget_usd);
  const spent = parseUsd(run.spent_usd);
  const open = signals.openReservationUsd ? parseUsd(signals.openReservationUsd) : 0n;
  const costGap = signals.costGapUsd ? parseUsd(signals.costGapUsd) : 0n;
  const costIsFinal =
    run.cost_is_complete &&
    !signals.reservationUnresolved &&
    !(run.status !== "running" && signals.unsettledOperations > 0);
  const overrun = spent > approved || signals.overrunDetected;
  const isExtended = approved > initial;
  const failed = run.status === "failed" || run.outcome === "failed";
  const startedAt = new Date(run.started_at);
  const endedAt = run.ended_at ? new Date(run.ended_at) : null;
  const durationSec = endedAt ? Math.round((endedAt.getTime() - startedAt.getTime()) / 1000) : null;

  const reasons: Reason[] = [];
  if (!costIsFinal) {
    reasons.push({
      tone: "critical",
      text:
        open > 0n
          ? `עלות לא סופית: ${formatUsd(open)} שוריינו ולא סוכמו — לא ידוע אם חויבנו (והעלות עשויה להיות גבוהה יותר)`
          : `עלות לא סופית: ${formatUsd(spent)} הוא חסם תחתון בלבד`,
    });
  }
  if (overrun) {
    reasons.push({
      tone: "critical",
      text: `ההוצאה ${formatUsd(spent)} עברה את התקרה ${formatUsd(approved)} (${formatPercent(percentOf(spent, approved))})`,
    });
  }
  if (costGap !== 0n) {
    reasons.push({
      tone: "critical",
      text: `פער לא מוסבר של ${formatGap(costGap)} בין העלות המדווחת לסכום עלויות הסוכנים`,
    });
  }
  if (failed) {
    reasons.push(
      signals.failureReason
        ? { tone: "critical", text: `הריצה נכשלה: ${signals.failureReason}`, isolate: signals.failureReason }
        : { tone: "critical", text: "הריצה נכשלה" },
    );
  }
  if (signals.approvalDenied) {
    reasons.push({
      tone: "critical",
      text:
        signals.approvalDeniedReason === "timeout_no_response"
          ? "בקשה להרחבת תקציב לא נענתה (פג הזמן)"
          : "בקשה להרחבת תקציב נדחתה",
    });
  }
  if (signals.budgetExhausted) {
    const n = signals.nodesNotRun;
    reasons.push({
      tone: "critical",
      text: n === null ? "התקציב מוצה" : `התקציב מוצה — ${n === 1 ? "סוכן אחד לא הופעל" : `${n} סוכנים לא הופעלו`}`,
    });
  }
  if (signals.downgrades.length > 0) {
    reasons.push({ tone: "warning", text: `איכות הורדה כדי להיכנס לתקציב: ${signals.downgrades.join("; ")}` });
  }
  if (isExtended) {
    const by = signals.extensionApprovedBy ? ` (אישר: ${signals.extensionApprovedBy})` : "";
    reasons.push({
      tone: "warning",
      text: `התקרה הורחבה באמצע הריצה מ-${formatUsd(initial)} ל-${formatUsd(approved)}${by}; ההוצאה היא ${formatPercent(percentOf(spent, initial))} מהתקציב המקורי`,
    });
  }
  if (signals.nodesMissingUsage) {
    reasons.push({ tone: "info", text: "לחלק מהסוכנים אין רשומות קריאה — נתוני שימוש חסרים" });
  }
  const timeout = signals.failureReason ? /after (\d+)s/.exec(signals.failureReason) : null;
  if (timeout && durationSec !== null && Number(timeout[1]) > durationSec) {
    reasons.push({
      tone: "info",
      text: `שגיאת timeout של ${timeout[1]} שנ׳ אינה תואמת משך ריצה של ${durationSec} שנ׳ — אי-התאמה בנתונים`,
    });
  }

  const verdict = pickVerdict(run, signals, overrun, costIsFinal, costGap);
  return {
    id: run.run_id,
    title: run.title,
    requestedBy: run.requested_by,
    status: run.status,
    outcome: run.outcome,
    verdict,
    verdictLabel: verdict === "partial" && signals.budgetExhausted ? PARTIAL_EXHAUSTED_LABEL : VERDICT[verdict].label,
    tone: verdict === "running" && reasons.some((r) => r.tone === "critical") ? "critical" : VERDICT[verdict].tone,
    reasons,
    initial,
    approved,
    spent,
    openReservation: open,
    costIsFinal,
    isExtended,
    pctOfApproved: percentOf(spent, approved),
    pctOfInitial: percentOf(spent, initial),
    startedAt,
    endedAt,
    durationSec,
  };
}

const dateFormat = new Intl.DateTimeFormat("he-IL", {
  timeZone: "Asia/Jerusalem",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

export function formatDate(d: Date): string {
  return dateFormat.format(d);
}

export function formatDuration(seconds: number | null): string {
  if (seconds === null) return "טרם הסתיימה";
  if (seconds < 60) return `${seconds} שנ׳`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m < 60) return s ? `${m} דק׳ ${s} שנ׳` : `${m} דק׳`;
  return `${Math.floor(m / 60)} שע׳ ${m % 60} דק׳`;
}

/** Attention first, then newest. The default order a manager scans in. */
export const TONE_ORDER: Record<Tone, number> = { critical: 0, warning: 1, neutral: 2, ok: 3 };

export type SortKey = "attention" | "started" | "budget";

export function compare(a: RunRow, b: RunRow, key: SortKey): number {
  const newest = b.startedAt.getTime() - a.startedAt.getTime();
  if (key === "started") return newest;
  if (key === "budget") return (b.pctOfApproved ?? -1) - (a.pctOfApproved ?? -1) || newest;
  return TONE_ORDER[a.tone] - TONE_ORDER[b.tone] || newest;
}
