import type { FamilyEvidenceViewDto, InvestigationLinkDto, ResultDto, RuntimeTraceEvent } from "../api/types";

export type ReplayPresentationStage = "SOURCE" | "OBSERVATION" | "VISIBILITY" | "ROUTING" | "EVALUATION" | "RESULT" | "FAMILY" | "RELATION";
export type ReplayPresentationStep = {
  key: string;
  stage: ReplayPresentationStage;
  observationId: string | null;
  focusObservationId: string | null;
  sourceObservationIds: string[];
  eventSequences: number[];
  resultIds: string[];
  familyViewIds: string[];
  linkIds: string[];
};
export type PresentationMode = "normal" | "fast" | "instant";
export type PlayerState = { stepIndex: number; paused: boolean; followLive: boolean; selectedObservationId: string | null };
export type PlayerAction = { type: "RESET" } | { type: "ADVANCE"; stepCount: number } | { type: "PAUSE" } | { type: "RESUME" } | { type: "SHOW_FINAL"; stepCount: number } | { type: "SELECT_OBSERVATION"; observationId: string } | { type: "FOLLOW_LIVE" };

function appendPresentationStep(steps: ReplayPresentationStep[], step: ReplayPresentationStep) {
  const previous = steps.at(-1);
  const canCombine = previous && previous.stage === step.stage
    && (step.stage === "ROUTING" || step.stage === "EVALUATION" || step.stage === "RESULT")
    && previous.observationId === step.observationId
    && previous.focusObservationId === step.focusObservationId
    && previous.sourceObservationIds.join("\u0000") === step.sourceObservationIds.join("\u0000");
  if (!previous || !canCombine) { steps.push(step); return; }
  previous.eventSequences.push(...step.eventSequences);
  previous.resultIds.push(...step.resultIds);
}

/** Build a judge-facing sequence exclusively from observed trace and durable evidence. */
export function buildReplayPresentationSteps(
  events: RuntimeTraceEvent[],
  results: ResultDto[],
  familyViews: FamilyEvidenceViewDto[],
  links: InvestigationLinkDto[],
): ReplayPresentationStep[] {
  const steps: ReplayPresentationStep[] = [];
  const resultIds = new Set(results.map((result) => result.result_id));
  const resultById = new Map(results.map((result) => [result.result_id, result]));
  const orderedEvents = [...events].sort((left, right) => left.sequence - right.sequence);
  const routedObservationIds = new Set(orderedEvents.filter((event) => event.kind === "ROUTED" && event.observation_id).map((event) => event.observation_id));
  const persistedResultIds = new Set(orderedEvents.filter((event) => event.kind === "RESULT_PERSISTED" && event.result_id).map((event) => event.result_id));
  const replayObservationIds = new Set(orderedEvents.filter((event) => event.kind === "OBSERVATION_CREATED" && event.observation_id).map((event) => event.observation_id));
  const fallbackResultsAfterSequence = new Map<number, ResultDto[]>();
  const allSourceRecordsAccepted = orderedEvents.filter((event) => event.kind === "SOURCE_RECORD_ACCEPTED").length >= replayObservationIds.size;
  for (const result of allSourceRecordsAccepted ? results : []) {
    if (persistedResultIds.has(result.result_id) || !result.source_observation_ids.length
      || !result.source_observation_ids.every((sourceId) => replayObservationIds.has(sourceId))) continue;
    const sourceEvents = orderedEvents.filter((event) => result.source_observation_ids.includes(event.observation_id || ""));
    const afterSequence = Math.max(0, ...sourceEvents.filter((event) => ["ANALYTIC_EVALUATING", "ANALYTIC_READINESS", "ANALYTIC_EVALUATED", "ADMISSION_REJECTED"].includes(event.kind)).map((event) => event.sequence));
    const rows = fallbackResultsAfterSequence.get(afterSequence) ?? [];
    rows.push(result);
    fallbackResultsAfterSequence.set(afterSequence, rows);
  }
  for (const event of orderedEvents) {
    let stage: Exclude<ReplayPresentationStage, "FAMILY" | "RELATION"> | null = null;
    if (event.kind === "SOURCE_RECORD_ACCEPTED") stage = "SOURCE";
    else if (event.kind === "OBSERVATION_CREATED") stage = "OBSERVATION";
    else if (event.kind === "VISIBILITY_EVALUATED") stage = "VISIBILITY";
    else if (event.kind === "ROUTED") stage = "ROUTING";
    else if (["ANALYTIC_EVALUATING", "ANALYTIC_READINESS", "ANALYTIC_EVALUATED", "ADMISSION_REJECTED"].includes(event.kind)) stage = "EVALUATION";
    else if (event.kind === "RESULT_PERSISTED" && event.result_id && resultIds.has(event.result_id)) stage = "RESULT";
    if (!stage) continue;
    const result = stage === "RESULT" && event.result_id ? resultById.get(event.result_id) : undefined;
    const sourceObservationIds = result?.source_observation_ids ?? event.source_observation_ids ?? [];
    const focusObservationId = stage === "RESULT"
      ? sourceObservationIds.length === 1 ? sourceObservationIds[0]! : null
      : event.observation_id;
    appendPresentationStep(steps, {
      key: `${event.sequence}:${stage}`,
      stage,
      observationId: focusObservationId,
      focusObservationId,
      sourceObservationIds: [...sourceObservationIds],
      eventSequences: [event.sequence],
      resultIds: stage === "RESULT" && event.result_id ? [event.result_id] : [],
      familyViewIds: [],
      linkIds: [],
    });
    // A completed trace with no ROUTED event for an observation means its
    // zero-route outcome is known. Keep it visible as a brief terminal route step.
    if (event.kind === "VISIBILITY_EVALUATED" && event.observation_id && !routedObservationIds.has(event.observation_id)) {
      appendPresentationStep(steps, { key: `${event.sequence}:NO_ROUTE`, stage: "ROUTING", observationId: event.observation_id, focusObservationId: event.observation_id, sourceObservationIds: [event.observation_id], eventSequences: [], resultIds: [], familyViewIds: [], linkIds: [] });
    }
    for (const result of fallbackResultsAfterSequence.get(event.sequence) ?? []) {
      const sourceObservationIds = [...result.source_observation_ids];
      const focusObservationId = sourceObservationIds.length === 1 ? sourceObservationIds[0]! : null;
      appendPresentationStep(steps, { key: `durable:${result.result_id}`, stage: "RESULT", observationId: focusObservationId, focusObservationId, sourceObservationIds, eventSequences: [], resultIds: [result.result_id], familyViewIds: [], linkIds: [] });
    }
  }

  for (const result of fallbackResultsAfterSequence.get(0) ?? []) {
    const sourceObservationIds = [...result.source_observation_ids];
    const focusObservationId = sourceObservationIds.length === 1 ? sourceObservationIds[0]! : null;
    appendPresentationStep(steps, { key: `durable:${result.result_id}`, stage: "RESULT", observationId: focusObservationId, focusObservationId, sourceObservationIds, eventSequences: [], resultIds: [result.result_id], familyViewIds: [], linkIds: [] });
  }

  if (familyViews.length) steps.push({ key: "family", stage: "FAMILY", observationId: null, focusObservationId: null, sourceObservationIds: [...new Set(familyViews.flatMap((view) => view.source_observation_ids))], eventSequences: [], resultIds: [], familyViewIds: familyViews.map((view) => view.family_view_id), linkIds: [] });
  if (links.length) steps.push({ key: "relation", stage: "RELATION", observationId: null, focusObservationId: null, sourceObservationIds: [...new Set(links.flatMap((link) => link.shared_source_observation_ids))], eventSequences: [], resultIds: [], familyViewIds: [], linkIds: links.map((link) => link.link_id) });
  return steps;
}

export function presentationDurationMs(scenario: string, sourceType: string, observationCount: number, mode: PresentationMode) {
  if (mode === "instant") return 0;
  const id = scenario.toLowerCase();
  const pcap = /pcap/i.test(sourceType) || id.includes("raw_pcap");
  let total = pcap ? 14000 : id.includes("mixed_ddos_recon") ? 9500 : id.includes("c2_recurrence") ? 10500 : observationCount <= 1 ? 6000 : 7000 + Math.max(0, observationCount - 1) * 550;
  total = Math.max(pcap ? 12000 : 5000, Math.min(pcap ? 16000 : id.includes("mixed_ddos_recon") ? 11000 : id.includes("c2_recurrence") ? 12000 : 9000, total));
  return mode === "fast" ? Math.max(1600, Math.round(total * 0.35)) : total;
}

export function presentationSchedule(steps: ReplayPresentationStep[], scenario: string, sourceType: string, observationCount: number, mode: PresentationMode) {
  const weights: Record<ReplayPresentationStage, number> = { SOURCE: 0.8, OBSERVATION: 1.2, VISIBILITY: 0.9, ROUTING: 2.4, EVALUATION: 1.3, RESULT: 1.2, FAMILY: 1.25, RELATION: 0.9 };
  const totalWeight = steps.reduce((sum, step) => sum + weights[step.stage], 0);
  if (!totalWeight) return [];
  return steps.map((step) => Math.round(presentationDurationMs(scenario, sourceType, observationCount, mode) * weights[step.stage] / totalWeight));
}

export function advancePlayer(state: PlayerState, stepCount: number): PlayerState {
  if (state.paused || state.stepIndex + 1 >= stepCount) return state;
  return { ...state, stepIndex: state.stepIndex + 1 };
}
export function pausePlayer(state: PlayerState): PlayerState { return { ...state, paused: true }; }
export function resumePlayer(state: PlayerState): PlayerState { return { ...state, paused: false }; }
export function showFinalPlayerState(state: PlayerState, stepCount: number): PlayerState { return { ...state, stepIndex: stepCount - 1, paused: false }; }
export function selectObservation(state: PlayerState, observationId: string): PlayerState { return { ...state, followLive: false, selectedObservationId: observationId }; }
export function resumeLiveFocus(state: PlayerState): PlayerState { return { ...state, followLive: true, selectedObservationId: null }; }
export function playerReducer(state: PlayerState, action: PlayerAction): PlayerState {
  switch (action.type) {
    case "RESET": return { stepIndex: -1, paused: false, followLive: true, selectedObservationId: null };
    case "ADVANCE": return advancePlayer(state, action.stepCount);
    case "PAUSE": return pausePlayer(state);
    case "RESUME": return resumePlayer(state);
    case "SHOW_FINAL": return showFinalPlayerState(state, action.stepCount);
    case "SELECT_OBSERVATION": return selectObservation(state, action.observationId);
    case "FOLLOW_LIVE": return resumeLiveFocus(state);
  }
}

export function groupFamilyEpisodes(views: FamilyEvidenceViewDto[]) {
  const groups = new Map<string, { family: string; views: FamilyEvidenceViewDto[]; viewIds: string[]; resultIds: string[] }>();
  for (const view of views) {
    const group = groups.get(view.family) ?? { family: view.family, views: [], viewIds: [], resultIds: [] };
    group.views.push(view);
    group.viewIds.push(view.family_view_id);
    group.resultIds.push(...view.source_result_ids);
    groups.set(view.family, group);
  }
  return [...groups.values()];
}

export function groupRelationsByFamilyPair(links: InvestigationLinkDto[], views: FamilyEvidenceViewDto[]) {
  const viewById = new Map(views.map((view) => [view.family_view_id, view]));
  type RelationGroup = { leftFamily: string; rightFamily: string; links: InvestigationLinkDto[]; linkIds: string[]; sharedObservationIds: string[] };
  const groups = new Map<string, RelationGroup>();
  for (const link of links) {
    const left = viewById.get(link.left_family_view_id)?.family;
    const right = viewById.get(link.right_family_view_id)?.family;
    if (!left || !right) continue;
    const orderedFamilies = [left, right].sort((a, b) => a.localeCompare(b));
    const leftFamily = orderedFamilies[0] ?? left;
    const rightFamily = orderedFamilies[1] ?? right;
    const key = `${leftFamily}\u0000${rightFamily}`;
    const group = groups.get(key) ?? { leftFamily, rightFamily, links: [], linkIds: [], sharedObservationIds: [] };
    group.links.push(link);
    group.linkIds.push(link.link_id);
    group.sharedObservationIds.push(...link.shared_source_observation_ids);
    groups.set(key, group);
  }
  return [...groups.values()];
}
