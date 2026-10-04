// Test-only: the real JSON fixtures, loaded the same way the page does.
import { readFileSync } from "node:fs";
import path from "node:path";
import { signalsFromDetail } from "./runs";
import type { RunDetail, RunListSignals, RunsResponse } from "./types";

const DATA = path.resolve(__dirname, "../../../data");

export const { runs } = JSON.parse(readFileSync(path.join(DATA, "runs.json"), "utf-8")) as RunsResponse;

export const signals: Record<string, RunListSignals> = Object.fromEntries(
  runs.map((r) => {
    const d = JSON.parse(readFileSync(path.join(DATA, "runs", `${r.run_id}.json`), "utf-8")) as RunDetail;
    return [r.run_id, signalsFromDetail(d)];
  }),
);
