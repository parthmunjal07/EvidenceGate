import { describe, expect, it } from "vitest";
import type { FamilyEvidenceViewDto, InvestigationLinkDto, ResultDto, RuntimeTraceEvent, ScenarioDto } from "../api/types";
import { JUDGE_DEMOS, judgeDemoScenarios, validateJudgeDemo } from "./judgeDemos";

const scenarios = JUDGE_DEMOS.map((demo) => ({ id: demo.id, label: demo.title, family: demo.families.join(" / "), source_type: demo.sourceLabel })) satisfies ScenarioDto[];
const result = (id: string): ResultDto => ({ result_id: id, source_observation_ids: ["obs-a"] } as ResultDto);
const view = (family: string): FamilyEvidenceViewDto => ({ family, family_view_id: family, source_result_ids: [], source_observation_ids: ["obs-a"] } as unknown as FamilyEvidenceViewDto);
const trace = [
  { sequence: 1, kind: "OBSERVATION_CREATED", observation_id: "obs-a" },
  { sequence: 2, kind: "ROUTED", observation_id: "obs-a" },
] as RuntimeTraceEvent[];
const makeLink = (id: string) => ({ link_id: id } as InvestigationLinkDto);

describe("judge demo contracts", () => {
  it("exposes only the curated five in normal mode and gates DGA on verified readiness", () => {
    const available = judgeDemoScenarios([...scenarios, { id: "internal", label: "internal", family: "test", source_type: "NDJSON" }], false);
    expect(available.map((item) => item.id)).toEqual(JUDGE_DEMOS.map((item) => item.id));
    expect(available[0]).toMatchObject({ recommended: true, label: "DDoS + Recon fan-out" });
    expect(available.find((item) => item.id === "dga_lexical")?.unavailableReason).toBe("DGA model unavailable in this deployment");
  });

  it("exposes internal scenarios only when the explicit development toggle is enabled", () => {
    const available = judgeDemoScenarios([...scenarios, { id: "internal", label: "internal", family: "test", source_type: "NDJSON" }], true, true);
    expect(available.some((item) => item.id === "internal")).toBe(true);
  });

  it("fails closed when a finalized demo misses a deterministic expectation", () => {
    const demo = JUDGE_DEMOS.find((item) => item.id === "mixed_ddos_recon")!;
    const resultState = validateJudgeDemo(demo, { observations: 2, results: [result("r1")], familyViews: [view("DDoS")], links: [], trace, traceAvailable: true, runtimeCompleted: true });
    expect(resultState.ok).toBe(false);
    expect(resultState.reasons).toContain("Expected 8 source-linked Results; received 1");
    expect(resultState.reasons).toContain("Expected family evidence for Reconnaissance");
    expect(resultState.reasons).toContain("Expected 1 factual relationships; received 0");
  });

  it("accepts the raw PCAP contract only when all required runtime facts are present", () => {
    const demo = JUDGE_DEMOS.find((item) => item.id === "raw_pcap_ddos_recon")!;
    const familyViews = [view("DDoS"), view("Reconnaissance")];
    const outcome = { observations: 11, results: Array.from({ length: 35 }, (_, index) => result("r" + index)), familyViews, links: [makeLink("1"), makeLink("2"), makeLink("3")], trace, traceAvailable: true, runtimeCompleted: true };
    expect(validateJudgeDemo(demo, outcome)).toEqual({ ok: true, reasons: [] });
    expect(validateJudgeDemo(demo, { ...outcome, traceAvailable: false }).ok).toBe(false);
  });
});
