import type { FamilyEvidenceViewDto, InvestigationLinkDto, ResultDto, RuntimeTraceEvent, ScenarioDto } from "../api/types";

export type JudgeDemoContract = {
  id: string;
  title: string;
  purpose: string;
  sourceLabel: "Controlled observations" | "Recorded PCAP";
  episodeSummary: string[];
  expectedRecords: number;
  expectedRoutes: number;
  expectedFamilyViews: number;
  expectedZeroRouteObservations: number;
  maxTraceEvents: number;
  expectedResults?: number;
  minResults?: number;
  expectedObservations?: number;
  minObservations?: number;
  families: string[];
  expectedRelations?: number;
  needsDga?: boolean;
};

export const JUDGE_DEMOS: JudgeDemoContract[] = [
  { id: "mixed_ddos_recon", title: "DDoS + Recon fan-out", purpose: "A controlled packet episode shows zero-to-many independent DDoS and Recon routing.", sourceLabel: "Controlled observations", episodeSummary: ["12 packet observations", "12 s source window", "TCP · UDP · ICMP · other IP", "2 no-route observations"], expectedRecords: 12, expectedObservations: 12, expectedRoutes: 60, expectedZeroRouteObservations: 2, expectedResults: 65, expectedFamilyViews: 17, expectedRelations: 8, maxTraceEvents: 500, families: ["DDoS", "Reconnaissance"] },
  { id: "ddos_one_way", title: "One-way SYN visibility", purpose: "Forward initiation facts remain visible while reverse packet evidence is unavailable.", sourceLabel: "Controlled observations", episodeSummary: ["8 packet observations", "8 s source window", "5 distinct TCP SYN attempts", "reverse facts unavailable"], expectedRecords: 8, expectedObservations: 8, expectedRoutes: 37, expectedZeroRouteObservations: 2, expectedResults: 40, expectedFamilyViews: 11, expectedRelations: 5, maxTraceEvents: 500, families: ["DDoS"] },
  { id: "c2_recurrence", title: "C2 recurrence", purpose: "Flow history builds across repeated observations before recurrence evidence appears.", sourceLabel: "Controlled observations", episodeSummary: ["7 flow observations", "4 min 11 s source window", "3 observed peers", "forward flow facts · reverse facts unavailable"], expectedRecords: 7, expectedObservations: 7, expectedRoutes: 14, expectedZeroRouteObservations: 0, expectedResults: 14, expectedFamilyViews: 10, expectedRelations: 7, maxTraceEvents: 500, families: ["C2 / Beaconing", "Data Transfer"] },
  { id: "dga_lexical", title: "DGA + DNS", purpose: "Each DNS observation produces independent lexical and structural evidence.", sourceLabel: "Controlled observations", episodeSummary: ["6 DNS observations", "6 controlled query names", "A · AAAA · UDP", "clear DNS fields available"], expectedRecords: 6, expectedObservations: 6, expectedRoutes: 12, expectedZeroRouteObservations: 0, expectedResults: 12, expectedFamilyViews: 6, expectedRelations: 0, maxTraceEvents: 500, families: ["DGA + DNS"], needsDga: true },
  { id: "raw_pcap_ddos_recon", title: "Recorded PCAP", purpose: "A controlled classic PCAP becomes canonical packet observations and linked evidence.", sourceLabel: "Recorded PCAP", episodeSummary: ["18 recorded packets", "2 s capture window", "11 observed endpoints", "5 no-route observations"], expectedRecords: 18, expectedObservations: 18, expectedRoutes: 71, expectedZeroRouteObservations: 5, expectedResults: 58, expectedFamilyViews: 15, expectedRelations: 8, maxTraceEvents: 500, families: ["DDoS", "Reconnaissance"] },
];

export type DemoOutcome = { records: number; observations: number; results: ResultDto[]; familyViews: FamilyEvidenceViewDto[]; links: InvestigationLinkDto[]; trace: RuntimeTraceEvent[]; traceAvailable: boolean; runtimeCompleted: boolean };
export type DemoValidation = { ok: boolean; reasons: string[] };

export function judgeDemoScenarios(scenarios: ScenarioDto[], dgaReady: boolean, exposeInternal = false): (ScenarioDto & { demo?: JudgeDemoContract; unavailableReason?: string; recommended?: boolean })[] {
  const demos = exposeInternal ? scenarios.map((scenario) => {
    const demo = JUDGE_DEMOS.find((item) => item.id === scenario.id);
    return { ...scenario, ...(demo ? { demo } : {}) };
  }) : JUDGE_DEMOS.flatMap((demo) => {
    const scenario = scenarios.find((item) => item.id === demo.id);
    return scenario ? [{ ...scenario, label: demo.title, source_type: demo.sourceLabel, demo, recommended: demo.id === "mixed_ddos_recon", ...(demo.needsDga && !dgaReady ? { unavailableReason: "DGA model unavailable in this deployment" } : {}) }] : [];
  });
  return demos;
}

export function validateJudgeDemo(demo: JudgeDemoContract, outcome: DemoOutcome): DemoValidation {
  const reasons: string[] = [];
  const families = new Set(outcome.familyViews.map((view) => normalizeDemoFamily(view.family)));
  const routeEvents = outcome.trace.filter((event) => event.kind === "ROUTED");
  const created = outcome.trace.filter((event) => event.kind === "OBSERVATION_CREATED");
  const routedIds = new Set(routeEvents.flatMap((event) => event.observation_id ? [event.observation_id] : []));
  if (!outcome.runtimeCompleted) reasons.push("Runtime did not complete");
  if (!outcome.traceAvailable) reasons.push("Runtime trace is unavailable or incomplete");
  if (outcome.records !== demo.expectedRecords) reasons.push(`Expected ${demo.expectedRecords} source records; received ${outcome.records}`);
  if (outcome.trace.length > demo.maxTraceEvents) reasons.push(`Trace has ${outcome.trace.length} events; limit is ${demo.maxTraceEvents}`);
  if (routeEvents.length !== demo.expectedRoutes) reasons.push(`Expected ${demo.expectedRoutes} analytic routes; received ${routeEvents.length}`);
  if (outcome.observations - routedIds.size !== demo.expectedZeroRouteObservations) reasons.push(`Expected ${demo.expectedZeroRouteObservations} zero-route observations; received ${outcome.observations - routedIds.size}`);
  if (outcome.familyViews.length !== demo.expectedFamilyViews) reasons.push(`Expected ${demo.expectedFamilyViews} family evidence views; received ${outcome.familyViews.length}`);
  if (created.length === 0) reasons.push("No observations were emitted");
  if (demo.expectedObservations !== undefined && outcome.observations !== demo.expectedObservations) reasons.push(`Expected ${demo.expectedObservations} observations; received ${outcome.observations}`);
  if (demo.minObservations !== undefined && outcome.observations < demo.minObservations) reasons.push(`Expected at least ${demo.minObservations} observations; received ${outcome.observations}`);
  if (demo.expectedResults !== undefined && outcome.results.length !== demo.expectedResults) reasons.push(`Expected ${demo.expectedResults} source-linked Results; received ${outcome.results.length}`);
  if (demo.minResults !== undefined && outcome.results.length < demo.minResults) reasons.push(`Expected at least ${demo.minResults} source-linked Results; received ${outcome.results.length}`);
  for (const family of demo.families) if (![...families].some((actual) => actual.includes(normalizeDemoFamily(family)))) reasons.push(`Expected family evidence for ${family}`);
  if (demo.expectedRelations !== undefined && outcome.links.length !== demo.expectedRelations) reasons.push(`Expected ${demo.expectedRelations} factual relationships; received ${outcome.links.length}`);
  if (created.some((event) => !event.observation_id) || routeEvents.some((event) => !event.observation_id)) reasons.push("Trace contains an observation event without source context");
  if (created.some((event) => !event.canonical_observation)) reasons.push("A canonical observation presentation is missing");
  if (outcome.results.some((result) => !result.source_observation_ids.length)) reasons.push("A source-linked Result has no source observation IDs");
  return { ok: reasons.length === 0, reasons };
}

function normalizeDemoFamily(value: string) {
  const family = value.toLowerCase();
  if (family.includes("ddos") || family.includes("dos")) return "ddos";
  if (family.includes("recon")) return "reconnaissance";
  if (family.includes("c2") || family.includes("beacon")) return "c2";
  if (family.includes("dga") || family.includes("dns")) return "dga dns";
  return family;
}
