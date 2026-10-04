import { formatPercent, formatUsd, maxMicro, ratioForDisplay } from "@/lib/money";
import type { RunRow } from "@/lib/runs";

/**
 * Spent vs. ceiling. The text line carries the information; the bar only repeats it
 * (aria-hidden), so nothing depends on seeing the colour or the shape.
 *
 * - overrun: the part beyond the ceiling is drawn past a ceiling tick, never clipped at 100%
 * - extended ceiling: a tick marks where the ORIGINAL budget ended
 * - cost not final: a hatched segment for the open reservation — an estimate, not a worst case
 */
export function BudgetMeter({ run }: { run: RunRow }) {
  const scale = maxMicro(maxMicro(run.approved, run.spent + run.openReservation), 1n);
  const spentW = ratioForDisplay(run.spent > run.approved ? run.approved : run.spent, scale);
  const overW = run.spent > run.approved ? ratioForDisplay(run.spent - run.approved, scale) : 0;
  const unknownW = ratioForDisplay(run.openReservation, scale);
  const ceilingAt = ratioForDisplay(run.approved, scale);
  const initialAt = run.isExtended ? ratioForDisplay(run.initial, scale) : null;

  const pct = run.pctOfApproved === null ? "—" : `${run.pctOfApproved}%`;
  const atLeast = run.costIsFinal ? "" : "לפחות ";
  const fill =
    run.tone === "critical" ? "bg-critical" : run.tone === "warning" ? "bg-warning" : run.tone === "neutral" ? "bg-neutral" : "bg-ok";

  return (
    <div className="min-w-44">
      <p className="text-sm leading-6">
        {atLeast}
        <bdi dir="ltr" className="font-semibold tabular-nums">{formatUsd(run.spent)}</bdi>
        <span className="text-muted"> מתוך </span>
        <bdi dir="ltr" className="tabular-nums">{formatUsd(run.approved)}</bdi>
        <span className="text-muted"> · </span>
        <span className={run.spent > run.approved ? "font-bold text-critical-text" : "tabular-nums"}>
          {atLeast}
          <bdi dir="ltr">{pct}</bdi>
        </span>
        {run.status === "running" && <span className="text-muted"> (עד כה)</span>}
      </p>
      {/* The bar grows from the right, like the text around it. */}
      <div aria-hidden="true" className="relative mt-1 h-2 w-full rounded-full bg-track">
        <div className={`absolute inset-y-0 right-0 rounded-full ${fill}`} style={{ width: `${spentW * 100}%` }} />
        {overW > 0 && (
          <div
            className="absolute inset-y-0 rounded-l-full bg-critical bg-stripes"
            style={{ right: `${ceilingAt * 100}%`, width: `${overW * 100}%` }}
          />
        )}
        {unknownW > 0 && (
          <div
            title="שריון פתוח"
            className="absolute inset-y-0 rounded-l-full border border-dashed border-critical bg-stripes"
            style={{ right: `${(spentW + overW) * 100}%`, width: `${unknownW * 100}%` }}
          />
        )}
        {ceilingAt < 1 && (
          <span className="absolute -inset-y-1 w-0.5 bg-ink" style={{ right: `${ceilingAt * 100}%` }} />
        )}
        {initialAt !== null && (
          <span className="absolute -inset-y-1 w-0.5 bg-warning-text" style={{ right: `${initialAt * 100}%` }} />
        )}
      </div>
      {run.isExtended && (
        <p className="mt-1 text-xs text-warning-text">
          <span aria-hidden="true">▲</span> תקציב מקורי <bdi dir="ltr">{formatUsd(run.initial)}</bdi> · נוצלו{" "}
          {formatPercent(run.pctOfInitial)} ממנו
        </p>
      )}
      {run.openReservation > 0n && (
        <p className="mt-1 text-xs text-critical-text">
          <span aria-hidden="true">?</span> שריון פתוח <bdi dir="ltr">{formatUsd(run.openReservation)}</bdi> — לא ידוע
          אם חויב (העלות עשויה להיות גבוהה יותר)
        </p>
      )}
    </div>
  );
}
