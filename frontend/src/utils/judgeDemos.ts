import type { FamilyEvidenceViewDto, InvestigationLinkDto, ResultDto, RuntimeTraceEvent, ScenarioDto } from "../api/types";

export type JudgeDemoContract = {
  id: string; title: string; purpose: string; sourceLabel: string; episodeSummary: string[];
  expectedRecords: number; expectedRoutes: number; expectedFamilyViews: number;
  expectedZeroRouteObservations: number; maxTraceEvents: number; expectedResults: number;
  expectedObservations: number; families: string[]; expectedRelations: number; needsDga: boolean;
  assetVersion: string;
};
export type DemoOutcome = { records: number; observations: number; results: ResultDto[]; familyViews: FamilyEvidenceViewDto[]; links: InvestigationLinkDto[]; trace: RuntimeTraceEvent[]; traceAvailable: boolean; runtimeCompleted: boolean };
export type DemoValidation = { ok: boolean; reasons: string[] };
export type DemoScenario = ScenarioDto & { demo?: JudgeDemoContract; unavailableReason?: string; recommended?: boolean };

export function demoContractFromScenario(s: ScenarioDto): JudgeDemoContract | null {
  if (!s.asset_version || !s.demo_title || s.expected_records == null || s.expected_observations == null || s.expected_routes == null || s.expected_results == null || s.expected_family_views == null || s.expected_relations == null || s.expected_zero_route_observations == null || s.max_trace_events == null) return null;
  return { id:s.id, title:s.demo_title, purpose:s.demo_purpose ?? "", sourceLabel:s.source_label ?? s.source_type, episodeSummary:s.episode_summary ?? [], expectedRecords:s.expected_records, expectedObservations:s.expected_observations, expectedRoutes:s.expected_routes, expectedResults:s.expected_results, expectedFamilyViews:s.expected_family_views, expectedRelations:s.expected_relations, expectedZeroRouteObservations:s.expected_zero_route_observations, maxTraceEvents:s.max_trace_events, needsDga:s.needs_dga ?? false, assetVersion:s.asset_version, families:s.family.split("/").map(x=>x.trim()).filter(Boolean) };
}

export function judgeDemoScenarios(scenarios: ScenarioDto[], dgaReady: boolean, exposeInternal = false): DemoScenario[] {
  return scenarios.flatMap<DemoScenario>((scenario) => {
    const demo = demoContractFromScenario(scenario);
    if (!demo) return exposeInternal ? [{...scenario}] : [];
    return [{ ...scenario, label: demo.title, source_type: demo.sourceLabel, demo, recommended: demo.id === "mixed_ddos_recon", ...(demo.needsDga && !dgaReady ? { unavailableReason: "DGA model unavailable in this deployment" } : {}) }];
  });
}

export function validateScopedEvidence(views: FamilyEvidenceViewDto[], links: InvestigationLinkDto[]) {
  const ids = new Set(views.map(v=>v.family_view_id));
  return links.every(link => ids.has(link.left_family_view_id) && ids.has(link.right_family_view_id)) && (views.length > 0 || links.length === 0);
}
export function validateDemoVersions(frontendSha: string, backendSha: string, scenario: ScenarioDto, contract: JudgeDemoContract | null) {
  return { buildMismatch: frontendSha === "unknown" || backendSha === "unknown" || frontendSha !== backendSha, assetMismatch: !contract || !scenario.asset_version || scenario.asset_version !== contract.assetVersion };
}

export function validateJudgeDemo(demo: JudgeDemoContract, outcome: DemoOutcome): DemoValidation {
  const reasons: string[] = [];
  const families = new Set(outcome.familyViews.map((view) => normalizeDemoFamily(view.family)));
  const routeEvents = outcome.trace.filter((event) => event.kind === "ROUTED");
  const created = outcome.trace.filter((event) => event.kind === "OBSERVATION_CREATED");
  const routedIds = new Set(routeEvents.flatMap((event) => event.observation_id ? [event.observation_id] : []));
  if (!outcome.runtimeCompleted) reasons.push("Runtime did not complete");
  if (!outcome.traceAvailable) reasons.push("Runtime trace is unavailable or incomplete");
  if (!validateScopedEvidence(outcome.familyViews, outcome.links)) reasons.push("Derived family and relationship evidence is inconsistent");
  if (outcome.records !== demo.expectedRecords) reasons.push(`Expected ${demo.expectedRecords} source records; received ${outcome.records}`);
  if (outcome.trace.length > demo.maxTraceEvents) reasons.push(`Trace has ${outcome.trace.length} events; limit is ${demo.maxTraceEvents}`);
  if (routeEvents.length !== demo.expectedRoutes) reasons.push(`Expected ${demo.expectedRoutes} analytic routes; received ${routeEvents.length}`);
  if (outcome.observations - routedIds.size !== demo.expectedZeroRouteObservations) reasons.push(`Expected ${demo.expectedZeroRouteObservations} zero-route observations; received ${outcome.observations - routedIds.size}`);
  if (outcome.familyViews.length !== demo.expectedFamilyViews) reasons.push(`Expected ${demo.expectedFamilyViews} family evidence views; received ${outcome.familyViews.length}`);
  if (created.length === 0) reasons.push("No observations were emitted");
  if (outcome.observations !== demo.expectedObservations) reasons.push(`Expected ${demo.expectedObservations} observations; received ${outcome.observations}`);
  if (outcome.results.length !== demo.expectedResults) reasons.push(`Expected ${demo.expectedResults} source-linked Results; received ${outcome.results.length}`);
  for (const family of demo.families) if (![...families].some((actual) => actual.includes(normalizeDemoFamily(family)))) reasons.push(`Expected family evidence for ${family}`);
  if (outcome.links.length !== demo.expectedRelations) reasons.push(`Expected ${demo.expectedRelations} factual relationships; received ${outcome.links.length}`);
  if (created.some((event) => !event.observation_id || !event.canonical_observation) || routeEvents.some((event) => !event.observation_id)) reasons.push("Trace is missing canonical source context");
  if (outcome.results.some((result) => !result.source_observation_ids.length)) reasons.push("A source-linked Result has no source observation IDs");
  return { ok: reasons.length === 0, reasons };
}
function normalizeDemoFamily(value: string) { const family = value.toLowerCase(); if (family.includes("ddos") || family.includes("dos")) return "ddos"; if (family.includes("recon")) return "reconnaissance"; if (family.includes("c2") || family.includes("beacon")) return "c2"; if (family.includes("dga") || family.includes("dns")) return "dga dns"; return family; }
