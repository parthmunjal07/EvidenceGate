import { describe, expect, it } from "vitest";
import type { ResultDto, RuntimeTraceEvent } from "../api/types";
import { newPersistedReplayRows, sourceLinkedReplayResults } from "./replayAttribution";

const result = (id: string, sourceIds: string[]) => ({
  result_id: id,
  source_observation_ids: sourceIds,
}) as ResultDto;
const event = (kind: string, observation_id: string | null): RuntimeTraceEvent => ({
  sequence: 1,
  kind,
  occurred_at: "2026-09-26T00:00:00Z",
  observation_id,
  observation_type: "PACKET",
  lane_id: "ddos.a",
  mechanism: "DDoS",
  readiness: null,
  reason: null,
  result_id: null,
  source_observation_ids: [],
});

describe("replay source lineage attribution", () => {
  it("excludes durable Results that were created by unrelated observations", () => {
    const linked = sourceLinkedReplayResults(
      [result("current", ["observation-a"]), result("unrelated", ["observation-old"])],
      [event("OBSERVATION_CREATED", "observation-a")],
    );
    expect(linked.map((item) => item.result_id)).toEqual(["current"]);
  });

  it("separates source-linked Results from newly inserted rows on deterministic reruns", () => {
    const linked = [result("fixture-result", ["observation-a"])];
    expect(newPersistedReplayRows(linked, new Set(["fixture-result"]))).toBe(0);
    expect(newPersistedReplayRows(linked, new Set())).toBe(1);
  });
});
