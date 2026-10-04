import { readFile } from "node:fs/promises";
import path from "node:path";
import { signalsFromDetail } from "./runs";
import type { RunDetail, RunListSignals, RunsResponse, RunSummary } from "./types";

// A static file today, an HTTP endpoint tomorrow — only this module changes.
const DATA_DIR = process.env.RUNS_DATA_DIR ?? path.join(process.cwd(), "..", "data");

export class DataError extends Error {}

function assertRuns(value: unknown): asserts value is RunsResponse {
  const runs = (value as RunsResponse | null)?.runs;
  if (!Array.isArray(runs)) throw new DataError("runs.json: missing `runs` array");
  for (const r of runs as unknown[]) {
    const run = r as Partial<RunSummary>;
    if (typeof run.run_id !== "string" || typeof run.spent_usd !== "string" || typeof run.approved_budget_usd !== "string") {
      throw new DataError(`runs.json: malformed run ${JSON.stringify(run.run_id ?? r)}`);
    }
  }
}

export async function loadRuns(): Promise<{ runs: RunSummary[]; signals: Record<string, RunListSignals> }> {
  const raw: unknown = JSON.parse(await readFile(path.join(DATA_DIR, "runs.json"), "utf-8"));
  assertRuns(raw);
  const entries = await Promise.all(
    raw.runs.map(async (r) => {
      try {
        const detail = JSON.parse(await readFile(path.join(DATA_DIR, "runs", `${r.run_id}.json`), "utf-8")) as RunDetail;
        return [r.run_id, signalsFromDetail(detail)] as const;
      } catch {
        return null; // a missing detail file degrades the row, it does not break the table
      }
    }),
  );
  return { runs: raw.runs, signals: Object.fromEntries(entries.filter((e) => e !== null)) };
}
