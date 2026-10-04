// Shapes from data/DATA-CONTRACT.md. Money stays `string` at this boundary.

export type RunStatus = "pending" | "running" | "completed" | "partial" | "failed";
export type RunOutcome = "succeeded" | "partial" | "failed" | null;

export interface RunSummary {
  run_id: string;
  title: string;
  requested_by: string;
  status: RunStatus;
  outcome: RunOutcome;
  initial_budget_usd: string;
  approved_budget_usd: string;
  spent_usd: string;
  started_at: string;
  ended_at: string | null;
  agent_count: number;
  cost_is_complete: boolean;
}

export interface RunsResponse {
  runs: RunSummary[];
}

export interface RunEvent {
  at: string;
  type: string;
  payload: Record<string, unknown> | null;
}

export interface RunNode {
  node_id: string;
  agent_name: string;
  cost_usd: string;
}

export interface RunOperation {
  operation_id: string;
  node_id: string;
  estimated_usd: string;
  actual_usd: string | null;
  settled: boolean;
}

export interface RunDetail extends Omit<RunSummary, "agent_count"> {
  nodes: RunNode[];
  operations: RunOperation[];
  events: RunEvent[];
}

/**
 * Facts that live only in the per-run detail file but change how a run should read
 * in the list. Plain JSON so it can cross the server → client boundary.
 * In production this belongs in the list endpoint itself (see README).
 */
export interface RunListSignals {
  downgrades: string[];
  extensionApprovedBy: string | null;
  openReservationUsd: string | null;
  reservationUnresolved: boolean;
  unsettledOperations: number;
  overrunDetected: boolean;
  costGapUsd: string | null;
  nodesMissingUsage: boolean;
  budgetExhausted: boolean;
  nodesNotRun: number | null;
  approvalDenied: boolean;
  approvalDeniedReason: string | null;
  failureReason: string | null;
}
