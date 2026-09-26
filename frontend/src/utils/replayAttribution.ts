import type { ResultDto, RuntimeTraceEvent } from "../api/types";

export function sourceLinkedReplayResults(
  durableResults: ResultDto[],
  trace: RuntimeTraceEvent[],
) {
  const observationIds = new Set(
    trace
      .filter((event) => event.kind === "OBSERVATION_CREATED" && event.observation_id)
      .map((event) => event.observation_id!),
  );
  return durableResults.filter((result) =>
    result.source_observation_ids.some((id) => observationIds.has(id)),
  );
}

export function newPersistedReplayRows(
  sourceLinkedResults: ResultDto[],
  baselineIds: Set<string>,
) {
  return new Set(
    sourceLinkedResults
      .filter((result) => !baselineIds.has(result.result_id))
      .map((result) => result.result_id),
  ).size;
}
