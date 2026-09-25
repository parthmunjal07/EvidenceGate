import { describe, expect, it } from "vitest";
import type { RuntimeTraceEvent } from "../api/types";
import {
  latestReadinessByObservationLane,
  fetchFinalRuntimeTrace,
  mergeRuntimeTraceEvents,
  observationLaneKey,
  replayJustCompleted,
} from "./runtimeTrace";

const event = (
  sequence: number,
  kind: string,
  observation_id: string,
  lane_id = "recon.h",
  readiness: string | null = null,
): RuntimeTraceEvent => ({
  sequence,
  kind,
  occurred_at: "2026-09-26T00:00:00Z",
  observation_id,
  observation_type: "DNS",
  lane_id,
  mechanism: "RECON-H",
  readiness,
  reason: null,
  result_id: null,
  source_observation_ids: [],
});

describe("runtime trace presentation", () => {
  it("scopes readiness to the exact observation and lane", () => {
    const latest = latestReadinessByObservationLane([
      event(1, "ANALYTIC_READINESS", "observation-a", "recon.h", "READY"),
      event(2, "ROUTED", "observation-b"),
    ]);

    expect(latest.get(observationLaneKey("observation-a", "recon.h"))?.readiness).toBe("READY");
    expect(latest.get(observationLaneKey("observation-b", "recon.h"))).toBeUndefined();
  });

  it("recognizes replay completion for a final trace drain", () => {
    expect(replayJustCompleted("RUNNING", "COMPLETED")).toBe(true);
    expect(replayJustCompleted("IDLE", "COMPLETED")).toBe(false);
  });

  it("merges a final drain by sequence without duplicating polled events", () => {
    const first = event(4, "ANALYTIC_EVALUATED", "observation-a");
    const final = event(5, "RESULT_PERSISTED", "observation-a");
    expect(mergeRuntimeTraceEvents([first], [first, final])).toEqual([first, final]);
  });

  it("fetches the final trace after completion using the last cursor", async () => {
    const first = event(4, "ANALYTIC_EVALUATED", "observation-a");
    const final = event(5, "RESULT_PERSISTED", "observation-a");
    const fetchTrace = async (after: number) => {
      expect(after).toBe(4);
      return { events: [first, final], latest_sequence: 5 };
    };

    const update = await fetchFinalRuntimeTrace("RUNNING", "COMPLETED", 4, fetchTrace);
    expect(update?.events).toEqual([first, final]);
    expect(await fetchFinalRuntimeTrace("IDLE", "COMPLETED", 4, fetchTrace)).toBeNull();
  });
});
