import type {
  FamilyEvidenceViewDto,
  InvestigationLinkDto,
  ReplayStatusResponse,
  ResultDto,
  RuntimeTraceEvent,
} from "../api/types";
import { sourceLinkedReplayResults } from "./replayAttribution";

export const LATEST_REPLAY_MARKER_KEY = "evidencegate.latest-replay-lineage";

export type LatestReplayMarker = {
  scenario: string;
  sourceType: string;
  startedAt: string;
  finishedAt: string;
  startSequence: number;
  endSequence: number;
};

export function saveLatestReplayMarker(marker: LatestReplayMarker) {
  localStorage.setItem(LATEST_REPLAY_MARKER_KEY, JSON.stringify(marker));
}

export function clearLatestReplayMarker() {
  localStorage.removeItem(LATEST_REPLAY_MARKER_KEY);
}

export function loadLatestReplayMarker(): LatestReplayMarker | null {
  try {
    const value: unknown = JSON.parse(
      localStorage.getItem(LATEST_REPLAY_MARKER_KEY) ?? "null",
    );
    if (!value || typeof value !== "object") return null;
    const marker = value as Partial<LatestReplayMarker>;
    if (
      typeof marker.scenario !== "string" ||
      typeof marker.sourceType !== "string" ||
      typeof marker.startedAt !== "string" ||
      typeof marker.finishedAt !== "string" ||
      !Number.isInteger(marker.startSequence) ||
      !Number.isInteger(marker.endSequence) ||
      marker.startSequence! < 0 ||
      marker.endSequence! < marker.startSequence!
    )
      return null;
    return marker as LatestReplayMarker;
  } catch {
    return null;
  }
}

export function replayMarkerMatches(
  marker: LatestReplayMarker,
  replay: ReplayStatusResponse,
) {
  return (
    replay.state === "COMPLETED" &&
    replay.started_at === marker.startedAt &&
    replay.finished_at === marker.finishedAt &&
    replay.scenario === marker.scenario &&
    replay.source_type === marker.sourceType
  );
}

export function completeTraceRange(
  events: RuntimeTraceEvent[],
  marker: LatestReplayMarker,
  latestSequence: number,
) {
  if (latestSequence < marker.endSequence) return false;
  if (marker.startSequence === marker.endSequence) return events.length === 0;
  if (events.length !== marker.endSequence - marker.startSequence) return false;
  return events.every(
    (event, index) => event.sequence === marker.startSequence + index + 1,
  );
}

export function filterLatestReplayEvidence(
  durableResults: ResultDto[],
  trace: RuntimeTraceEvent[],
  views: FamilyEvidenceViewDto[],
  links: InvestigationLinkDto[],
) {
  const results = sourceLinkedReplayResults(durableResults, trace);
  const resultIds = new Set(results.map((result) => result.result_id));
  const familyViews = views.filter((view) =>
    view.source_result_ids.some((id) => resultIds.has(id)),
  );
  const viewIds = new Set(familyViews.map((view) => view.family_view_id));
  const investigations = links.filter(
    (link) =>
      viewIds.has(link.left_family_view_id) &&
      viewIds.has(link.right_family_view_id),
  );
  return { results, views: familyViews, links: investigations };
}
