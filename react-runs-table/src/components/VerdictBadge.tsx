import { TONE_LABEL, type Tone, VERDICT, type Verdict } from "@/lib/runs";

const TONE_CLASS: Record<Tone, string> = {
  critical: "bg-critical-bg text-critical-text ring-critical/40",
  warning: "bg-warning-bg text-warning-text ring-warning/40",
  ok: "bg-ok-bg text-ok-text ring-ok/40",
  neutral: "bg-neutral-bg text-neutral-text ring-neutral/40",
};

/** Icon + words + colour: each alone is enough to read the verdict. */
export function VerdictBadge({ verdict, label }: { verdict: Verdict; label?: string }) {
  const v = VERDICT[verdict];
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-md px-2 py-0.5 text-sm font-semibold ring-1 ring-inset ${TONE_CLASS[v.tone]}`}
    >
      <span aria-hidden="true">{v.icon}</span>
      {label ?? v.label}
      <span className="sr-only"> ({TONE_LABEL[v.tone]})</span>
    </span>
  );
}
