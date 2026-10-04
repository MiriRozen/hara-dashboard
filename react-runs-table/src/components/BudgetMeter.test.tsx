import { render, screen } from "@testing-library/react";
import { runs, signals } from "@/lib/fixtures";
import { toRunRow } from "@/lib/runs";
import type { RunSummary } from "@/lib/types";
import { BudgetMeter } from "./BudgetMeter";

const fixtureRow = (id: string) => toRunRow(runs.find((r) => r.run_id === id)!, signals[id]);

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

describe("<BudgetMeter />", () => {
  it("shows an open reservation, not an upper bound, when the cost is unknown", () => {
    const { container } = render(<BudgetMeter run={fixtureRow("run-9e21d4")} />);
    expect(container).toHaveTextContent(
      "? שריון פתוח $0.2600 — לא ידוע אם חויב (העלות עשויה להיות גבוהה יותר)",
    );
    expect(container.textContent).not.toMatch(/העלות בפועל עד/);
    expect(screen.getByText("?")).toHaveAttribute("aria-hidden", "true");
  });

  it("draws the open reservation after the overrun segment when both apply", () => {
    const run = toRunRow(
      { ...BASE, spent_usd: "1.500000", cost_is_complete: false },
      {
        downgrades: [],
        extensionApprovedBy: null,
        openReservationUsd: "0.500000",
        reservationUnresolved: true,
        unsettledOperations: 0,
        overrunDetected: false,
        costGapUsd: null,
        nodesMissingUsage: false,
        budgetExhausted: false,
        nodesNotRun: null,
        approvalDenied: false,
        approvalDeniedReason: null,
        failureReason: null,
      },
    );
    const { container } = render(<BudgetMeter run={run} />);
    // scale = spent + open = $2.00 → spent-to-ceiling 50%, overrun 25%, open reservation 25%
    const open = container.querySelector<HTMLElement>('[title="שריון פתוח"]')!;
    expect(open).not.toBeNull();
    expect(open.style.right).toBe("75%");
    expect(open.style.width).toBe("25%");
  });

  it("prints '—' for the share of a zero original budget", () => {
    const run = toRunRow({ ...BASE, initial_budget_usd: "0.000000" });
    const { container } = render(<BudgetMeter run={run} />);
    expect(container).toHaveTextContent("נוצלו — ממנו");
    expect(container.textContent).not.toMatch(/null|undefined|NaN/);
  });
});
