import { describe, expect, it } from "vitest";
import type { FamilyEvidenceViewDto, InvestigationLinkDto, ResultDto, RuntimeTraceEvent } from "../api/types";
import { normalizeFamilyName } from "./formatting";
import { advancePlayer, buildReplayPresentationSteps, groupFamilyEpisodes, groupRelationsByFamilyPair, pausePlayer, playerReducer, presentationDurationMs, presentationSchedule, resumeLiveFocus, resumePlayer, selectObservation, showFinalPlayerState, type PlayerState } from "./replayPresentation";

const traceEvent = (sequence: number, kind: string, observationId: string | null = null): RuntimeTraceEvent => ({
  sequence, kind, occurred_at: `2026-01-01T00:00:${String(sequence).padStart(2, "0")}Z`, observation_id: observationId,
  observation_type: observationId ? "PACKET" : null, lane_id: kind === "ROUTED" || kind.startsWith("ANALYTIC_") ? `lane-${observationId}` : null,
  mechanism: null, readiness: kind === "ANALYTIC_EVALUATED" ? "READY" : null, reason: null, result_id: null, source_observation_ids: [],
});
const result = (id: string, observationId: string): ResultDto => ({
  result_id: id, schema_version: "1", result_type: "REVIEW_FINDING", created_time: "2026-01-01T00:00:05Z", lane_id: `lane-${observationId}`,
  family: "DDoS", plugin_id: "test", plugin_version: "1", analytic_version: "1", governance_version: "1", entity_reference: "10.0.0.1",
  taxonomy: ["DOS", "DDoS", "evidence"], mechanism_id: "DDOS-CV-B0", status_snapshot: {} as ResultDto["status_snapshot"], claim_ceiling: "OBSERVED_EVIDENCE_ONLY",
  evidence: {}, evidence_items: [], missing_prerequisites: [], source_observation_ids: [observationId], source_ids: [], quality_snapshot: { packet_loss: "UNKNOWN", sampling: "UNKNOWN", parser: "UNKNOWN", capture_gap: "UNKNOWN" },
  visibility_snapshot: { available: [], unavailable: [], degraded: [] }, state_version: null, config_hash: null, parser_refs: [], model_refs: [], governing_ids: [], quality_refs: [], provenance_refs: [], evidence_interval: null, reason_code: null,
});
const view = (id: string, family: string, resultId: string, observationId: string): FamilyEvidenceViewDto => ({
  family_view_id: id, family, time_start: "2026-01-01T00:00:01Z", time_end: "2026-01-01T00:00:02Z", entity_references: [], source_result_ids: [resultId], source_observation_ids: [observationId],
  findings: [{ source_result_id: resultId, title: "Finding", statements: [], result_type: "REVIEW_FINDING" }], limitations: [], missing_evidence: [], visibility_summary: [], quality_summary: [],
});
const link = (id: string, left: string, right: string, observation: string): InvestigationLinkDto => ({ link_id: id, left_family_view_id: left, right_family_view_id: right, relation_types: [], shared_source_observation_ids: [observation], source_result_ids: [], claim_guard: [] });

describe("semantic replay presentation", () => {
  it("derives semantic steps from actual trace and durable Results without mutating runtime data", () => {
    const trace = [traceEvent(1, "SOURCE_RECORD_ACCEPTED"), traceEvent(2, "OBSERVATION_CREATED", "obs-a"), traceEvent(3, "VISIBILITY_EVALUATED", "obs-a"), traceEvent(4, "ROUTED", "obs-a"), traceEvent(5, "ANALYTIC_EVALUATED", "obs-a")];
    const results = [result("r-a", "obs-a")];
    const originalTrace = structuredClone(trace);
    const originalResults = structuredClone(results);
    const steps = buildReplayPresentationSteps(trace, results, [], []);
    expect(steps.map((item) => item.stage)).toEqual(["SOURCE", "OBSERVATION", "VISIBILITY", "ROUTING", "EVALUATION", "RESULT"]);
    expect(steps.find((item) => item.stage === "RESULT")?.resultIds).toEqual(["r-a"]);
    expect(trace).toEqual(originalTrace);
    expect(results).toEqual(originalResults);
  });

  it("does not invent composition or relation steps without derived records", () => {
    const steps = buildReplayPresentationSteps([traceEvent(1, "OBSERVATION_CREATED", "obs-a")], [], [], []);
    expect(steps.map((item) => item.stage)).toEqual(["OBSERVATION"]);
  });

  it("paces each supported episode within the requested presentation-only ranges", () => {
    expect(presentationDurationMs("dga_lexical", "NDJSON", 1, "normal")).toBeGreaterThanOrEqual(5000);
    expect(presentationDurationMs("dga_lexical", "NDJSON", 1, "normal")).toBeLessThanOrEqual(7000);
    expect(presentationDurationMs("mixed_ddos_recon", "NDJSON", 2, "normal")).toBeGreaterThanOrEqual(8000);
    expect(presentationDurationMs("mixed_ddos_recon", "NDJSON", 2, "normal")).toBeLessThanOrEqual(11000);
    expect(presentationDurationMs("c2_recurrence", "NDJSON", 3, "normal")).toBeGreaterThanOrEqual(9000);
    expect(presentationDurationMs("c2_recurrence", "NDJSON", 3, "normal")).toBeLessThanOrEqual(12000);
    expect(presentationDurationMs("raw_pcap_ddos_recon", "PCAP", 11, "normal")).toBeGreaterThanOrEqual(12000);
    expect(presentationDurationMs("raw_pcap_ddos_recon", "PCAP", 11, "normal")).toBeLessThanOrEqual(16000);
    expect(presentationDurationMs("raw_pcap_ddos_recon", "PCAP", 11, "instant")).toBe(0);
    const steps = buildReplayPresentationSteps([traceEvent(1, "OBSERVATION_CREATED", "obs-a")], [], [], []);
    expect(presentationSchedule(steps, "dga_lexical", "NDJSON", 1, "fast").every((delay) => delay >= 0)).toBe(true);
  });

  it("supports pause, resume, instant final state, manual selection and live focus", () => {
    const start: PlayerState = { stepIndex: 0, paused: false, followLive: true, selectedObservationId: null };
    expect(playerReducer(start, { type: "PAUSE" }).paused).toBe(true);
    expect(playerReducer(playerReducer(start, { type: "PAUSE" }), { type: "ADVANCE", stepCount: 4 }).stepIndex).toBe(0);
    expect(playerReducer(start, { type: "ADVANCE", stepCount: 4 }).stepIndex).toBe(1);
    expect(playerReducer(start, { type: "SHOW_FINAL", stepCount: 4 })).toMatchObject({ stepIndex: 3, paused: false });
    expect(playerReducer(start, { type: "SELECT_OBSERVATION", observationId: "obs-a" })).toMatchObject({ followLive: false, selectedObservationId: "obs-a" });
    expect(playerReducer(start, { type: "RESET" })).toMatchObject({ stepIndex: -1, followLive: true, selectedObservationId: null });
    expect(pausePlayer(start).paused).toBe(true);
    expect(advancePlayer(pausePlayer(start), 4).stepIndex).toBe(0);
    expect(advancePlayer(resumePlayer(pausePlayer(start)), 4).stepIndex).toBe(1);
    expect(showFinalPlayerState(start, 4)).toMatchObject({ stepIndex: 3, paused: false });
    expect(selectObservation(start, "obs-a")).toMatchObject({ followLive: false, selectedObservationId: "obs-a" });
    expect(resumeLiveFocus(selectObservation(start, "obs-a"))).toMatchObject({ followLive: true, selectedObservationId: null });
  });

  it("groups family episodes while retaining every view and source Result ID", () => {
    const views = [view("v1", "DDoS", "r1", "obs-a"), view("v2", "DDoS", "r2", "obs-b"), view("v3", "Reconnaissance", "r3", "obs-c")];
    const groups = groupFamilyEpisodes(views);
    expect(groups.find((group) => group.family === "DDoS")).toMatchObject({ viewIds: ["v1", "v2"], resultIds: ["r1", "r2"] });
  });

  it("groups reversed relation rows by unordered family pair without dropping link IDs", () => {
    const views = [view("d1", "DDoS", "r1", "obs-a"), view("r1", "Reconnaissance", "r2", "obs-b"), view("d2", "DDoS", "r3", "obs-c"), view("r2", "Reconnaissance", "r4", "obs-d")];
    const links = [link("l1", "d1", "r1", "obs-a"), link("l2", "r2", "d2", "obs-b"), link("l3", "d1", "r2", "obs-c")];
    const groups = groupRelationsByFamilyPair(links, views);
    expect(groups).toHaveLength(1);
    expect(groups[0]?.linkIds).toEqual(["l1", "l2", "l3"]);
    expect(groups[0]?.sharedObservationIds).toEqual(["obs-a", "obs-b", "obs-c"]);
  });

  it("normalizes analyst family labels", () => {
    expect(["DDoS evidence", "Reconnaissance evidence", "Ddos / reconnaissance", "C2", "DGA + DNS", "Encrypted sessions", "Data transfer"].map(normalizeFamilyName))
      .toEqual(["DDoS", "Reconnaissance", "DDoS + Reconnaissance", "C2 / Beaconing", "DGA + DNS", "Encrypted Sessions", "Data Transfer"]);
  });
});
