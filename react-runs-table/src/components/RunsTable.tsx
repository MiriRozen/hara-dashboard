"use client";

import { useId, useMemo, useRef, useState } from "react";
import { formatUsd, sumMicro } from "@/lib/money";
import {
  compare,
  formatDate,
  formatDuration,
  OUTCOME_LABEL,
  REASON_ICON,
  type RunRow,
  type SortKey,
  STATUS_LABEL,
  toRunRow,
} from "@/lib/runs";
import type { RunListSignals, RunStatus, RunSummary } from "@/lib/types";
import { BudgetMeter } from "./BudgetMeter";
import { VerdictBadge } from "./VerdictBadge";

type StatusFilter = "all" | RunStatus;

const STATUS_FILTERS: StatusFilter[] = ["all", "running", "completed", "partial", "failed", "pending"];
const SORT_LABEL: Record<SortKey, string> = {
  attention: "דורש בירור קודם",
  started: "החדשות קודם",
  budget: "ניצול תקציב (גבוה קודם)",
};

export interface RunsTableProps {
  runs: RunSummary[];
  /** Extra per-run facts from the detail endpoint; optional — the table works without them. */
  signals?: Record<string, RunListSignals>;
  /** Where a row links to. Omit to render titles as plain text. */
  runHref?: (runId: string) => string;
}

export function RunsTable({ runs, signals = {}, runHref }: RunsTableProps) {
  const [status, setStatus] = useState<StatusFilter>("all");
  const [attentionOnly, setAttentionOnly] = useState(false);
  const [sort, setSort] = useState<SortKey>("attention");
  const headingId = useId();
  const allFilterRef = useRef<HTMLButtonElement>(null);

  const rows = useMemo(() => runs.map((r) => toRunRow(r, signals[r.run_id])), [runs, signals]);

  const counts = useMemo(() => {
    const scoped = rows.filter((r) => !attentionOnly || r.tone === "critical");
    const c: Record<StatusFilter, number> = { all: scoped.length, pending: 0, running: 0, completed: 0, partial: 0, failed: 0 };
    for (const r of scoped) c[r.status] += 1;
    return c;
  }, [rows, attentionOnly]);

  const visible = useMemo(() => {
    const filtered = rows.filter(
      (r) => (status === "all" || r.status === status) && (!attentionOnly || r.tone === "critical"),
    );
    return filtered.sort((a, b) => compare(a, b, sort));
  }, [rows, status, attentionOnly, sort]);

  const totals = useMemo(() => {
    const spent = sumMicro(rows.map((r) => r.spent));
    const open = sumMicro(rows.map((r) => r.openReservation));
    return {
      spent,
      open,
      final: rows.every((r) => r.costIsFinal && r.status !== "running"),
      critical: rows.filter((r) => r.tone === "critical").length,
      warning: rows.filter((r) => r.tone === "warning").length,
      running: rows.filter((r) => r.status === "running").length,
    };
  }, [rows]);

  if (runs.length === 0) {
    return (
      <div role="status" className="rounded-xl border border-line bg-surface p-10 text-center">
        <p className="text-lg font-semibold">אין עדיין ריצות</p>
        <p className="text-muted">כשתופעל ריצה ראשונה היא תופיע כאן.</p>
      </div>
    );
  }

  return (
    <section aria-labelledby={headingId} className="space-y-4">
      <h2 id={headingId} className="sr-only">
        רשימת הריצות
      </h2>
      {/* ---- summary: every number here is exact, and says so when it is a lower bound */}
      <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="הוצאה כוללת">
          {!totals.final && <span className="text-base font-semibold">לפחות </span>}
          <bdi dir="ltr">{formatUsd(totals.spent)}</bdi>
          {totals.open > 0n && (
            <span className="block text-xs font-normal text-critical-text">
              + <bdi dir="ltr">{formatUsd(totals.open)}</bdi> בשריון פתוח
            </span>
          )}
        </Stat>
        <Stat label="דורשות בירור" tone="critical">
          <button
            type="button"
            aria-pressed={attentionOnly}
            aria-label={`הצג רק ${totals.critical} ריצות שדורשות בירור`}
            className="underline decoration-dotted underline-offset-4 hover:decoration-solid focus-visible:outline-2"
            onClick={() => {
              if (attentionOnly) {
                setAttentionOnly(false);
                return;
              }
              setAttentionOnly(true);
              setStatus("all");
            }}
          >
            <span aria-hidden="true">✖</span> {totals.critical} ריצות
          </button>
        </Stat>
        <Stat label="לידיעה (הרחבה / הורדת איכות)" tone="warning">
          <span aria-hidden="true">▲</span> {totals.warning} ריצות
        </Stat>
        <Stat label="בריצה כעת">
          <span aria-hidden="true">◔</span> {totals.running}
        </Stat>
      </dl>

      {/* ---- controls */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <div role="group" aria-label="סינון לפי מצב הריצה" className="flex flex-wrap gap-1.5">
          {STATUS_FILTERS.filter((f) => f === "all" || counts[f] > 0 || status === f).map((f) => (
            <button
              key={f}
              ref={f === "all" ? allFilterRef : undefined}
              type="button"
              aria-pressed={status === f}
              onClick={() => setStatus(f)}
              className="rounded-full border border-line px-3 py-1 text-sm aria-pressed:border-ink aria-pressed:bg-ink aria-pressed:text-surface"
            >
              {f === "all" ? "הכול" : STATUS_LABEL[f]} <span className="tabular-nums">({counts[f]})</span>
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={attentionOnly}
            onChange={(e) => setAttentionOnly(e.target.checked)}
            className="size-4 accent-ink"
          />
          רק ריצות שדורשות בירור
        </label>
        <label className="flex items-center gap-2 text-sm">
          מיון:
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as SortKey)}
            className="rounded-md border border-line bg-surface px-2 py-1"
          >
            {(Object.keys(SORT_LABEL) as SortKey[]).map((k) => (
              <option key={k} value={k}>
                {SORT_LABEL[k]}
              </option>
            ))}
          </select>
        </label>
      </div>

      <p aria-live="polite" className="sr-only">
        מוצגות {visible.length} מתוך {rows.length} ריצות
      </p>

      {visible.length === 0 ? (
        <div role="status" className="rounded-xl border border-dashed border-line bg-surface p-8 text-center">
          <p className="font-semibold">אין ריצות שתואמות לסינון</p>
          <button
            type="button"
            className="mt-2 text-sm underline"
            onClick={() => {
              setStatus("all");
              setAttentionOnly(false);
              allFilterRef.current?.focus();
            }}
          >
            ניקוי סינון
          </button>
        </div>
      ) : (
        // Below md the table collapses into stacked cards — no horizontal scrolling on phones.
        <table className="w-full border-separate border-spacing-0 text-right max-md:block">
          <caption className="sr-only">
            ריצות — מצב, תוצאה, עלות מול תקציב, מועד ומבקש. ממוין לפי {SORT_LABEL[sort]}.
          </caption>
          <thead className="max-md:sr-only">
            <tr className="text-sm text-muted">
              <Th>ריצה</Th>
              <Th>מצב ותוצאה</Th>
              <Th aria-sort={sort === "budget" ? "descending" : undefined}>עלות מול תקציב</Th>
              <Th aria-sort={sort === "started" ? "descending" : undefined}>מתי</Th>
              <Th>מי ביקש</Th>
            </tr>
          </thead>
          <tbody className="max-md:block max-md:space-y-3">
            {visible.map((r) => (
              <RunRowView key={r.id} run={r} href={runHref?.(r.id)} />
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function RunRowView({ run, href }: { run: RunRow; href?: string }) {
  const accent =
    run.tone === "critical" ? "border-r-critical" : run.tone === "warning" ? "border-r-warning" : "border-r-transparent";
  return (
    <tr className="align-top max-md:block max-md:rounded-xl max-md:border max-md:border-line max-md:bg-surface">
      <Td header label="ריצה" className={`border-r-4 ${accent} max-md:border-r-4`}>
        {href ? (
          <a href={href} className="font-semibold text-ink underline-offset-4 hover:underline">
            {run.title}
          </a>
        ) : (
          <span className="font-semibold">{run.title}</span>
        )}
        <bdi dir="ltr" className="block font-mono text-xs text-muted">
          {run.id}
        </bdi>
        {run.reasons.length > 0 && (
          <ul className="mt-2 space-y-1 text-xs">
            {run.reasons.map((reason) => (
              <li
                key={reason.text}
                className={
                  reason.tone === "critical"
                    ? "text-critical-text"
                    : reason.tone === "warning"
                      ? "text-warning-text"
                      : "text-muted"
                }
              >
                <span aria-hidden="true">{REASON_ICON[reason.tone]} </span>
                {reason.isolate ? (
                  <>
                    {reason.text.slice(0, reason.text.length - reason.isolate.length)}
                    <bdi dir="ltr">{reason.isolate}</bdi>
                  </>
                ) : (
                  reason.text
                )}
              </li>
            ))}
          </ul>
        )}
      </Td>
      <Td label="מצב ותוצאה">
        <VerdictBadge verdict={run.verdict} label={run.verdictLabel} />
        <span className="mt-1 block text-xs text-muted">
          מצב: {STATUS_LABEL[run.status]} · תוצאה: {run.outcome ? OUTCOME_LABEL[run.outcome] : "טרם נקבעה"}
        </span>
      </Td>
      <Td label="עלות מול תקציב">
        <BudgetMeter run={run} />
      </Td>
      <Td label="מתי">
        <time dateTime={run.startedAt.toISOString()} className="block tabular-nums">
          <bdi dir="ltr">{formatDate(run.startedAt)}</bdi>
        </time>
        <span className="text-xs text-muted">משך: {formatDuration(run.durationSec)}</span>
      </Td>
      <Td label="מי ביקש">{run.requestedBy}</Td>
    </tr>
  );
}

function Th({ children, ...rest }: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th scope="col" className="border-b border-line px-3 pb-2 font-medium" {...rest}>
      {children}
    </th>
  );
}

function Td({
  label,
  header = false,
  className = "",
  children,
}: {
  label: string;
  header?: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  const classes = `border-b border-line bg-surface px-3 py-3 max-md:block max-md:border-b-0 max-md:py-2 max-md:before:mb-1 max-md:before:block max-md:before:text-xs max-md:before:text-muted max-md:before:content-[attr(data-label)] ${className}`;
  return header ? (
    <th scope="row" data-label={label} className={`text-right font-normal ${classes}`}>
      {children}
    </th>
  ) : (
    <td data-label={label} className={classes}>
      {children}
    </td>
  );
}

function Stat({ label, tone, children }: { label: string; tone?: "critical" | "warning"; children: React.ReactNode }) {
  const color = tone === "critical" ? "text-critical-text" : tone === "warning" ? "text-warning-text" : "text-ink";
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <dt className="text-sm text-muted">{label}</dt>
      <dd className={`mt-1 text-2xl font-bold tabular-nums ${color}`}>{children}</dd>
    </div>
  );
}
