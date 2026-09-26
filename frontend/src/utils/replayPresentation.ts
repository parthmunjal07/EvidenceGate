import type { FamilyEvidenceViewDto, InvestigationLinkDto, ResultDto, RuntimeTraceEvent } from "../api/types";

export type ReplayPresentationStage = "SOURCE" | "OBSERVATION" | "VISIBILITY" | "ROUTING" | "EVALUATION" | "RESULT" | "FAMILY" | "RELATION";
export type ReplayPresentationStep = {
  key: string;
  stage: ReplayPresentationStage;
  observationId: string | null;
  eventSequences: number[];
  resultIds: string[];
  familyViewIds: string[];
  linkIds: string[];
};
export type PresentationMode = "normal" | "fast" | "instant";
export type PlayerState = { stepIndex: number; paused: boolean; followLive: boolean; selectedObservationId: string | null };
export type PlayerAction = { type: "RESET" } | { type: "ADVANCE"; stepCount: number } | { type: "PAUSE" } | { type: "RESUME" } | { type: "SHOW_FINAL"; stepCount: number } | { type: "SELECT_OBSERVATION"; observationId: string } | { type: "FOLLOW_LIVE" };

/** Build a judge-facing sequence exclusively from observed trace and durable evidence. */
export function buildReplayPresentationSteps(
  events: RuntimeTraceEvent[],
  results: ResultDto[],
  familyViews: FamilyEvidenceViewDto[],
  links: InvestigationLinkDto[],
): ReplayPresentationStep[] {
  const steps: ReplayPresentationStep[] = [];
  const resultIds = new Set(results.map((result) => result.result_id));
  const orderedEvents = [...events].sort((left, right) => left.sequence - right.sequence);
  for (const event of orderedEvents) {
    let stage: Exclude<ReplayPresentationStage, "FAMILY" | "RELATION"> | null = null;
    if (event.kind === "SOURCE_RECORD_ACCEPTED") stage = "SOURCE";
    else if (event.kind === "OBSERVATION_CREATED") stage = "OBSERVATION";
    else if (event.kind === "VISIBILITY_EVALUATED") stage = "VISIBILITY";
    else if (event.kind === "ROUTED") stage = "ROUTING";
    else if (["ANALYTIC_EVALUATING", "ANALYTIC_READINESS", "ANALYTIC_EVALUATED", "ADMISSION_REJECTED"].includes(event.kind)) stage = "EVALUATION";
    else if (event.kind === "RESULT_PERSISTED" && event.result_id && resultIds.has(event.result_id)) stage = "RESULT";
    if (!stage) continue;
    steps.push({
      key: `${event.sequence}:${stage}`,
      stage,
      observationId: event.observation_id,
      eventSequences: [event.sequence],
      resultIds: stage === "RESULT" && event.result_id ? [event.result_id] : [],
      familyViewIds: [],
      linkIds: [],
    });
  }

  if (familyViews.length) steps.push({ key: "family", stage: "FAMILY", observationId: null, eventSequences: [], resultIds: [], familyViewIds: familyViews.map((view) => view.family_view_id), linkIds: [] });
  if (links.length) steps.push({ key: "relation", stage: "RELATION", observationId: null, eventSequences: [], resultIds: [], familyViewIds: [], linkIds: links.map((link) => link.link_id) });
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
