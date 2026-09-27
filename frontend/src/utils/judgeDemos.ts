import type { FamilyEvidenceViewDto, InvestigationLinkDto, ResultDto, RuntimeTraceEvent, ScenarioDto } from "../api/types";

export type JudgeDemoContract = {
  id: string;
  title: string;
  purpose: string;
  sourceLabel: "Controlled observations" | "Recorded PCAP";
  expectedResults?: number;
  minResults?: number;
  expectedObservations?: number;
  minObservations?: number;
  families: string[];
  expectedRelations?: number;
  needsDga?: boolean;
};

export const JUDGE_DEMOS: JudgeDemoContract[] = [
  { id: "mixed_ddos_recon", title: "DDoS + Recon fan-out", purpose: "One passive observation reaches independent DDoS and reconnaissance analytics.", sourceLabel: "Controlled observations", expectedObservations: 2, expectedResults: 8, families: ["DDoS", "Reconnaissance"], expectedRelations: 1 },
  { id: "ddos_one_way", title: "One-way SYN visibility", purpose: "Missing reverse packet evidence remains an explicit limitation.", sourceLabel: "Controlled observations", expectedObservations: 2, expectedResults: 4, families: ["DDoS"], expectedRelations: 0 },
  { id: "c2_recurrence", title: "C2 recurrence", purpose: "Bounded observation history builds before recurrence evidence appears.", sourceLabel: "Controlled observations", minObservations: 3, minResults: 1, families: ["C2 / Beaconing"] },
  { id: "dga_lexical", title: "DGA + DNS", purpose: "Lexical model and DNS structure provide independent evidence.", sourceLabel: "Controlled observations", expectedObservations: 1, expectedResults: 2, families: ["DGA + DNS"], expectedRelations: 0, needsDga: true },
  { id: "raw_pcap_ddos_recon", title: "Recorded PCAP", purpose: "Recorded packets traverse the shared runtime and produce linked evidence.", sourceLabel: "Recorded PCAP", expectedObservations: 11, expectedResults: 35, families: ["DDoS", "Reconnaissance"], expectedRelations: 3 },
];

export type DemoOutcome = { observations: number; results: ResultDto[]; familyViews: FamilyEvidenceViewDto[]; links: InvestigationLinkDto[]; trace: RuntimeTraceEvent[]; traceAvailable: boolean; runtimeCompleted: boolean };
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
  if (!outcome.runtimeCompleted) reasons.push("Runtime did not complete");
  if (!outcome.traceAvailable) reasons.push("Runtime trace is unavailable or incomplete");
  if (created.length === 0) reasons.push("No observations were emitted");
  if (demo.expectedObservations !== undefined && outcome.observations !== demo.expectedObservations) reasons.push(`Expected ${demo.expectedObservations} observations; received ${outcome.observations}`);
  if (demo.minObservations !== undefined && outcome.observations < demo.minObservations) reasons.push(`Expected at least ${demo.minObservations} observations; received ${outcome.observations}`);
  if (demo.expectedResults !== undefined && outcome.results.length !== demo.expectedResults) reasons.push(`Expected ${demo.expectedResults} source-linked Results; received ${outcome.results.length}`);
  if (demo.minResults !== undefined && outcome.results.length < demo.minResults) reasons.push(`Expected at least ${demo.minResults} source-linked Results; received ${outcome.results.length}`);
  for (const family of demo.families) if (![...families].some((actual) => actual.includes(normalizeDemoFamily(family)))) reasons.push(`Expected family evidence for ${family}`);
  if (demo.expectedRelations !== undefined && outcome.links.length !== demo.expectedRelations) reasons.push(`Expected ${demo.expectedRelations} factual relationships; received ${outcome.links.length}`);
  if (created.some((event) => !event.observation_id) || routeEvents.some((event) => !event.observation_id)) reasons.push("Trace contains an observation event without source context");
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
