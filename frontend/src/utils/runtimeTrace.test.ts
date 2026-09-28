import { describe, expect, it } from "vitest";
import type { RuntimeTraceEvent } from "../api/types";
import {
  latestReadinessByObservationLane,
  fetchFinalRuntimeTrace,
  captureRuntimeTraceBaseline,
  advanceRuntimeTraceCursor,
  hasCompleteRuntimeTraceRange,
  hasRuntimeTraceGap,
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
  it("accepts a fully drained trace range and rejects missing events or a stale head", () => {
    const events = [
      event(11, "SOURCE_RECORD_ACCEPTED", "obs"),
      event(12, "OBSERVATION_CREATED", "obs"),
      event(13, "ROUTED", "obs"),
    ];
    expect(hasCompleteRuntimeTraceRange(events, 10, 13)).toBe(true);
    expect(
      hasCompleteRuntimeTraceRange(
        events.filter((item) => item.sequence !== 12),
        10,
        13,
      ),
    ).toBe(false);
    expect(hasCompleteRuntimeTraceRange(events, 10, 14)).toBe(false);
  });
  it("scopes readiness to the exact observation and lane", () => {
    const latest = latestReadinessByObservationLane([
      event(1, "ANALYTIC_READINESS", "observation-a", "recon.h", "READY"),
      event(2, "ROUTED", "observation-b"),
    ]);

    expect(
      latest.get(observationLaneKey("observation-a", "recon.h"))?.readiness,
    ).toBe("READY");
    expect(
      latest.get(observationLaneKey("observation-b", "recon.h")),
    ).toBeUndefined();
  });

  it("recognizes replay completion for a final trace drain", () => {
    expect(replayJustCompleted("RUNNING", "COMPLETED")).toBe(true);
    expect(replayJustCompleted("IDLE", "COMPLETED")).toBe(false);
  });

  it("merges a final drain by sequence without duplicating polled events", () => {
    const first = event(4, "ANALYTIC_EVALUATED", "observation-a");
    const final = event(5, "RESULT_PERSISTED", "observation-a");
    expect(mergeRuntimeTraceEvents([first], [first, final])).toEqual([
      first,
      final,
    ]);
  });

  it("captures a long-history baseline from one latest-sequence head request", async () => {
    const calls: Array<[number, number]> = [];
    const baseline = await captureRuntimeTraceBaseline(async (after, limit) => {
      calls.push([after, limit]);
      return {
        events: [event(1, "SOURCE_RECORD_ACCEPTED", "")],
        latest_sequence: 4500,
      };
    });
    expect(baseline).toBe(4500);
    expect(calls).toEqual([[0, 1]]);
  });

  it("starts after the 4500-event baseline and admits only new replay events", async () => {
    const baseline = await captureRuntimeTraceBaseline(async () => ({
      events: [],
      latest_sequence: 4500,
    }));
    const cursors: number[] = [];
    const replayEvents = [
      event(4501, "OBSERVATION_CREATED", "new-observation"),
      event(4502, "ROUTED", "new-observation"),
      event(4503, "RESULT_PERSISTED", "new-observation"),
    ];
    const page = async (after: number) => {
      cursors.push(after);
      return {
        events: replayEvents.filter((item) => item.sequence > after),
        latest_sequence: 4503,
      };
    };
    const first = await page(baseline);
    expect(first.events.map((item) => item.sequence)).toEqual([
      4501, 4502, 4503,
    ]);
    const cursor = advanceRuntimeTraceCursor(baseline, first.events);
    expect(cursor).toBe(4503);
    expect(cursors).toEqual([4500]);
    expect(hasRuntimeTraceGap(baseline, first.events)).toBe(false);
  });

  it("advances forward pagination by the last event received, not the global latest sequence", () => {
    const page = [
      event(101, "ROUTED", "observation-a"),
      event(200, "ROUTED", "observation-b"),
    ];
    expect(advanceRuntimeTraceCursor(100, page)).toBe(200);
    expect(advanceRuntimeTraceCursor(200, [])).toBe(200);
  });

  it("keeps true ring-buffer eviction as a detectable gap without fabricating events", () => {
    const retained = [event(5001, "ROUTED", "observation-retained")];
    expect(hasRuntimeTraceGap(4500, retained)).toBe(true);
    expect(
      mergeRuntimeTraceEvents([], retained).map((item) => item.sequence),
    ).toEqual([5001]);
  });

  it("fetches the final trace after completion using the last cursor", async () => {
    const first = event(4, "ANALYTIC_EVALUATED", "observation-a");
    const final = event(5, "RESULT_PERSISTED", "observation-a");
    const fetchTrace = async (after: number) => {
      expect(after).toBe(4);
      return { events: [first, final], latest_sequence: 5 };
    };

    const update = await fetchFinalRuntimeTrace(
      "RUNNING",
      "COMPLETED",
      4,
      fetchTrace,
    );
    expect(update?.events).toEqual([first, final]);
    expect(
      await fetchFinalRuntimeTrace("IDLE", "COMPLETED", 4, fetchTrace),
    ).toBeNull();
  });
});
