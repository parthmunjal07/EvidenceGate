import type { ObservationPresentationDto, ResultDto, RuntimeTraceEvent } from "../api/types";

const CACHE_KEY = "evidencegate.latest-replay-evidence";

export function clearReplayEvidenceCache(): void {
  try { sessionStorage.removeItem(CACHE_KEY); } catch { /* optional cache */ }
}

export function cacheReplayEvidence(events: RuntimeTraceEvent[], results: ResultDto[]): void {
  try {
    sessionStorage.setItem(CACHE_KEY, JSON.stringify({ events, results }));
  } catch {
    // Browser storage is a convenience for source navigation, not evidence authority.
  }
}

export function cachedObservationIds(sourceIds: string[]): string[] {
  const cache = readCache();
  if (!cache) return [];
  const available = new Set(cache.events.flatMap((event) => event.kind === "OBSERVATION_CREATED" && event.canonical_observation ? [event.canonical_observation.observation_id] : []));
  return sourceIds.filter((id) => available.has(id));
}

export function readCachedObservations(sourceIds: string[]): ObservationPresentationDto[] {
  const cache = readCache();
  if (!cache) return [];
  const available = new Map<string, ObservationPresentationDto>();
  for (const event of cache.events) {
    const observation = event.kind === "OBSERVATION_CREATED" ? event.canonical_observation : null;
    if (observation && !available.has(observation.observation_id)) available.set(observation.observation_id, observation);
  }
  return sourceIds.flatMap((id) => available.has(id) ? [available.get(id)!] : []);
}

export function readCachedObservation(id: string) {
  const cache = readCache();
  if (!cache) return null;
  const observationEvent = cache.events.find((event) => event.kind === "OBSERVATION_CREATED" && event.canonical_observation?.observation_id === id);
  const observation = observationEvent?.canonical_observation;
  if (!observation) return null;
  const source = cache.events.find((event) => event.kind === "SOURCE_RECORD_ACCEPTED" && event.source_record?.record_number === Number(observation.source_position))?.source_record ?? null;
  const routes = cache.events.filter((event) => event.kind === "ROUTED" && event.observation_id === id);
  const results = cache.results.filter((result) => result.source_observation_ids.includes(id));
  return { observation, source, routes, results };
}

function readCache(): { events: RuntimeTraceEvent[]; results: ResultDto[] } | null {
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw) as { events?: RuntimeTraceEvent[]; results?: ResultDto[] };
    return Array.isArray(value.events) && Array.isArray(value.results) ? { events: value.events, results: value.results } : null;
  } catch {
    return null;
  }
}
