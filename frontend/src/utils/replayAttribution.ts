import type { ResultDto, RuntimeTraceEvent } from "../api/types";

export function sourceLinkedReplayResults(
  durableResults: ResultDto[],
  trace: RuntimeTraceEvent[],
) {
  const durableById = new Map(
    durableResults.map((result) => [result.result_id, result]),
  );
  const observationIds = new Set(
    trace
      .filter(
        (event) => event.kind === "OBSERVATION_CREATED" && event.observation_id,
      )
      .map((event) => event.observation_id!),
  );
  const returned = new Set<string>();
  const persisted = trace
    .filter((event) => event.kind === "RESULT_PERSISTED" && event.result_id)
    .flatMap((event) => {
      const result = durableById.get(event.result_id!);
      if (
        !result ||
        returned.has(result.result_id) ||
        !result.source_observation_ids.length ||
        !result.source_observation_ids.some((sourceId) =>
          observationIds.has(sourceId),
        )
      )
        return [];
      returned.add(result.result_id);
      return [{ result, sequence: event.sequence }];
    });

  // Deterministic fixture reruns may find the exact Result already durable.
  // Such a no-op write emits no RESULT_PERSISTED event; link only rows whose
  // complete source set belongs to observations in this replay.
  const replayObservationSet = new Set(observationIds);
  const evaluatedSequenceByObservation = new Map<string, number>();
  for (const event of trace) {
    if (
      event.observation_id &&
      [
        "ANALYTIC_EVALUATING",
        "ANALYTIC_READINESS",
        "ANALYTIC_EVALUATED",
        "ADMISSION_REJECTED",
      ].includes(event.kind)
    ) {
      evaluatedSequenceByObservation.set(
        event.observation_id,
        Math.max(
          event.sequence,
          evaluatedSequenceByObservation.get(event.observation_id) ?? 0,
        ),
      );
    }
  }
  const replayLinked = durableResults.flatMap((result) => {
    if (
      returned.has(result.result_id) ||
      !result.source_observation_ids.length ||
      !result.source_observation_ids.every((sourceId) =>
        replayObservationSet.has(sourceId),
      )
    )
      return [];
    returned.add(result.result_id);
    const sourceSequences = result.source_observation_ids.map(
      (sourceId) => evaluatedSequenceByObservation.get(sourceId) ?? 0,
    );
    return [{ result, sequence: Math.max(...sourceSequences) }];
  });

  return [...persisted, ...replayLinked]
    .sort(
      (left, right) =>
        left.sequence - right.sequence ||
        left.result.result_id.localeCompare(right.result.result_id),
    )
    .map(({ result }) => result);
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
