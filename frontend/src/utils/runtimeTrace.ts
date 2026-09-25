import type { ReplayStatusResponse, RuntimeTraceEvent, RuntimeTraceResponse } from "../api/types";

export const observationLaneKey = (observationId: string, laneId: string) =>
  `${observationId}:${laneId}`;

export function latestReadinessByObservationLane(events: RuntimeTraceEvent[]) {
  const latest = new Map<string, RuntimeTraceEvent>();
  for (const event of events) {
    if (
      event.observation_id &&
      event.lane_id &&
      [
        "ADMISSION_REJECTED",
        "ANALYTIC_EVALUATING",
        "ANALYTIC_READINESS",
        "ANALYTIC_EVALUATED",
      ].includes(event.kind)
    ) {
      latest.set(observationLaneKey(event.observation_id, event.lane_id), event);
    }
  }
  return latest;
}

export function mergeRuntimeTraceEvents(
  current: RuntimeTraceEvent[],
  incoming: RuntimeTraceEvent[],
) {
  const bySequence = new Map<number, RuntimeTraceEvent>();
  for (const event of [...current, ...incoming]) bySequence.set(event.sequence, event);
  return [...bySequence.values()].sort((a, b) => a.sequence - b.sequence).slice(-500);
}

export function replayJustCompleted(
  previous: ReplayStatusResponse["state"] | undefined,
  current: ReplayStatusResponse["state"] | undefined,
) {
  return previous === "RUNNING" && current === "COMPLETED";
}

export async function fetchFinalRuntimeTrace(
  previous: ReplayStatusResponse["state"] | undefined,
  current: ReplayStatusResponse["state"] | undefined,
  cursor: number,
  fetchTrace: (after: number) => Promise<RuntimeTraceResponse>,
) {
  if (!replayJustCompleted(previous, current)) return null;
  return fetchTrace(cursor);
}
