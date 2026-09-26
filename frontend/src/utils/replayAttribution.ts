import type { ResultDto, RuntimeTraceEvent } from "../api/types";

export function sourceLinkedReplayResults(
  durableResults: ResultDto[],
  trace: RuntimeTraceEvent[],
) {
  const durableById = new Map(durableResults.map((result) => [result.result_id, result]));
  const observationIds = new Set(
    trace
      .filter((event) => event.kind === "OBSERVATION_CREATED" && event.observation_id)
      .map((event) => event.observation_id!),
  );
  const returned = new Set<string>();
  return trace
    .filter((event) => event.kind === "RESULT_PERSISTED" && event.result_id)
    .flatMap((event) => {
      const id = event.result_id!;
      const result = durableById.get(id);
      if (!result || returned.has(id) || !result.source_observation_ids.some((sourceId) => observationIds.has(sourceId))) return [];
      returned.add(id);
      return [result];
    });
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
