import { describe, expect, it } from "vitest";
import type { FamilyEvidenceViewDto, InvestigationLinkDto, ResultDto, RuntimeTraceEvent } from "../api/types";
import { normalizeFamilyName } from "./formatting";
import { advancePlayer, buildReplayPresentationSteps, groupFamilyEpisodes, groupRelationsByFamilyPair, pausePlayer, playerReducer, presentationDurationMs, presentationSchedule, resumeLiveFocus, resumePlayer, selectObservation, showFinalPlayerState, type PlayerState } from "./replayPresentation";
import { sourceLinkedReplayResults } from "./replayAttribution";

const traceEvent = (sequence: number, kind: string, observationId: string | null = null): RuntimeTraceEvent => ({
  sequence, kind, occurred_at: `2026-01-01T00:00:${String(sequence).padStart(2, "0")}Z`, observation_id: observationId,
  observation_type: observationId ? "PACKET" : null, lane_id: kind === "ROUTED" || kind.startsWith("ANALYTIC_") ? `lane-${observationId}` : null,
  mechanism: null, readiness: kind === "ANALYTIC_EVALUATED" ? "READY" : null, reason: null, result_id: null, source_observation_ids: [],
});
const result = (id: string, observationIds: string | string[]): ResultDto => {
  const sources = Array.isArray(observationIds) ? observationIds : [observationIds];
  return {
  result_id: id, schema_version: "1", result_type: "REVIEW_FINDING", created_time: "2026-01-01T00:00:05Z", lane_id: `lane-${sources[0]}`,
  family: "DDoS", plugin_id: "test", plugin_version: "1", analytic_version: "1", governance_version: "1", entity_reference: "10.0.0.1",
  taxonomy: ["DOS", "DDoS", "evidence"], mechanism_id: "DDOS-CV-B0", status_snapshot: {} as ResultDto["status_snapshot"], claim_ceiling: "OBSERVED_EVIDENCE_ONLY",
  evidence: {}, evidence_items: [], missing_prerequisites: [], source_ids: [], quality_snapshot: { packet_loss: "UNKNOWN", sampling: "UNKNOWN", parser: "UNKNOWN", capture_gap: "UNKNOWN" },
  visibility_snapshot: { available: [], unavailable: [], degraded: [] }, state_version: null, config_hash: null, parser_refs: [], model_refs: [], governing_ids: [], quality_refs: [], provenance_refs: [], evidence_interval: null, reason_code: null,
  source_observation_ids: sources,
  };
};
const view = (id: string, family: string, resultId: string, observationId: string): FamilyEvidenceViewDto => ({
  family_view_id: id, family, time_start: "2026-01-01T00:00:01Z", time_end: "2026-01-01T00:00:02Z", entity_references: [], source_result_ids: [resultId], source_observation_ids: [observationId],
  findings: [{ source_result_id: resultId, title: "Finding", statements: [], result_type: "REVIEW_FINDING" }], limitations: [], missing_evidence: [], visibility_summary: [], quality_summary: [],
});
const link = (id: string, left: string, right: string, observation: string): InvestigationLinkDto => ({ link_id: id, left_family_view_id: left, right_family_view_id: right, relation_types: [], shared_source_observation_ids: [observation], source_result_ids: [], claim_guard: [] });

describe("semantic replay presentation", () => {
  it("derives semantic steps from actual trace and durable Results without mutating runtime data", () => {
    const trace = [traceEvent(1, "SOURCE_RECORD_ACCEPTED"), traceEvent(2, "OBSERVATION_CREATED", "obs-a"), traceEvent(3, "VISIBILITY_EVALUATED", "obs-a"), traceEvent(4, "ROUTED", "obs-a"), traceEvent(5, "ANALYTIC_EVALUATED", "obs-a"), { ...traceEvent(6, "RESULT_PERSISTED"), result_id: "r-a", source_observation_ids: ["obs-a"] }];
    const results = [result("r-a", "obs-a")];
    const originalTrace = structuredClone(trace);
    const originalResults = structuredClone(results);
    const steps = buildReplayPresentationSteps(trace, results, [], []);
    expect(steps.map((item) => item.stage)).toEqual(["SOURCE", "OBSERVATION", "VISIBILITY", "ROUTING", "EVALUATION", "RESULT"]);
    expect(steps.find((item) => item.stage === "RESULT")?.resultIds).toEqual(["r-a"]);
    expect(steps.find((item) => item.stage === "RESULT")?.eventSequences).toEqual([6]);
    expect(trace).toEqual(originalTrace);
    expect(results).toEqual(originalResults);
  });

  it("reveals a stateful C2 Result only at its RESULT_PERSISTED trace event", () => {
    const history = [
      traceEvent(1, "OBSERVATION_CREATED", "obs-1"), traceEvent(2, "ROUTED", "obs-1"), traceEvent(3, "ANALYTIC_READINESS", "obs-1"),
      traceEvent(4, "OBSERVATION_CREATED", "obs-2"), traceEvent(5, "ROUTED", "obs-2"), traceEvent(6, "ANALYTIC_READINESS", "obs-2"),
      traceEvent(7, "OBSERVATION_CREATED", "obs-3"), traceEvent(8, "ROUTED", "obs-3"), traceEvent(9, "ANALYTIC_READINESS", "obs-3"),
    ];
    const recurrence = result("result-c2", ["obs-1", "obs-2", "obs-3"]);
    const persisted = { ...traceEvent(10, "RESULT_PERSISTED"), result_id: recurrence.result_id, source_observation_ids: [...recurrence.source_observation_ids] };
    const priorSteps = buildReplayPresentationSteps(history, [recurrence], [], []);
    expect(priorSteps.flatMap((step) => step.resultIds)).toEqual([]);
    expect(buildReplayPresentationSteps(history.slice(0, 3), [recurrence], [], []).flatMap((step) => step.resultIds)).toEqual([]);
    expect(buildReplayPresentationSteps(history.slice(0, 6), [recurrence], [], []).flatMap((step) => step.resultIds)).toEqual([]);
    const complete = buildReplayPresentationSteps([...history, persisted], [recurrence], [], []);
    const reveal = complete.find((step) => step.stage === "RESULT");
    expect(reveal).toMatchObject({ observationId: null, focusObservationId: null, sourceObservationIds: ["obs-1", "obs-2", "obs-3"], eventSequences: [10], resultIds: ["result-c2"] });
    expect(complete.at(-1)?.eventSequences).toEqual([10]);
    expect(recurrence.source_observation_ids).toEqual(["obs-1", "obs-2", "obs-3"]);
  });

  it("attributes only persisted Results and keeps their trace order and full lineage", () => {
    const first = result("first", ["obs-1", "obs-2"]);
    const second = result("second", ["obs-2", "obs-3"]);
    const linked = sourceLinkedReplayResults([first, second], [
      traceEvent(1, "OBSERVATION_CREATED", "obs-1"), traceEvent(2, "OBSERVATION_CREATED", "obs-2"), traceEvent(3, "OBSERVATION_CREATED", "obs-3"),
      { ...traceEvent(4, "RESULT_PERSISTED"), result_id: "second", source_observation_ids: [...second.source_observation_ids] },
      { ...traceEvent(5, "RESULT_PERSISTED"), result_id: "first", source_observation_ids: [...first.source_observation_ids] },
    ]);
    expect(linked.map((item) => item.result_id)).toEqual(["second", "first"]);
    expect(linked[0]?.source_observation_ids).toEqual(["obs-2", "obs-3"]);
  });

  it("reveals a stateless DGA Result at its matching persistence event", () => {
    const observation = traceEvent(1, "OBSERVATION_CREATED", "obs-dga");
    const persisted = { ...traceEvent(4, "RESULT_PERSISTED"), result_id: "result-dga", source_observation_ids: ["obs-dga"] };
    const dga = result("result-dga", "obs-dga");
    expect(buildReplayPresentationSteps([observation], [dga], [], []).flatMap((step) => step.resultIds)).toEqual([]);
    const steps = buildReplayPresentationSteps([observation, traceEvent(2, "ROUTED", "obs-dga"), traceEvent(3, "ANALYTIC_EVALUATED", "obs-dga"), persisted], [dga], [], []);
    expect(steps.at(-1)).toMatchObject({ stage: "RESULT", observationId: "obs-dga", focusObservationId: "obs-dga", sourceObservationIds: ["obs-dga"], eventSequences: [4], resultIds: ["result-dga"] });
    expect(dga.source_observation_ids).toEqual(["obs-dga"]);
  });

  it("keeps a null-observation persistence step focused on its durable source observation", () => {
    const source = result("null-observation-result", "obs-3");
    const trace = [traceEvent(1, "OBSERVATION_CREATED", "obs-3"), { ...traceEvent(2, "RESULT_PERSISTED"), result_id: source.result_id, source_observation_ids: ["obs-3"] }];
    expect(buildReplayPresentationSteps(trace, [source], [], []).at(-1)).toMatchObject({ observationId: "obs-3", focusObservationId: "obs-3", sourceObservationIds: ["obs-3"] });
  });

  it("presents an existing durable Result after source evaluation when rerun persistence is a no-op", () => {
    const source = result("already-durable-result", "obs-repeat");
    const events = [traceEvent(1, "SOURCE_RECORD_ACCEPTED"), traceEvent(2, "OBSERVATION_CREATED", "obs-repeat"), traceEvent(3, "ROUTED", "obs-repeat"), traceEvent(4, "ANALYTIC_EVALUATED", "obs-repeat")];
    const steps = buildReplayPresentationSteps(events, [source], [], []);
    expect(steps.at(-1)).toMatchObject({ stage: "RESULT", eventSequences: [], resultIds: ["already-durable-result"], sourceObservationIds: ["obs-repeat"], focusObservationId: "obs-repeat" });
  });

  it("groups adjacent same-observation fan-out steps while retaining every route", () => {
    const events = [traceEvent(1, "OBSERVATION_CREATED", "obs-fan"), traceEvent(2, "ROUTED", "obs-fan"), traceEvent(3, "ROUTED", "obs-fan")];
    const steps = buildReplayPresentationSteps(events, [], [], []);
    const routing = steps.filter((step) => step.stage === "ROUTING");
    expect(routing).toHaveLength(1);
    expect(routing[0]?.eventSequences).toEqual([2, 3]);
  });

  it("inserts a terminal routing step for a completed zero-route observation", () => {
    const trace = [traceEvent(1, "OBSERVATION_CREATED", "obs-zero"), traceEvent(2, "VISIBILITY_EVALUATED", "obs-zero"), traceEvent(3, "OBSERVATION_CREATED", "obs-next")];
    const steps = buildReplayPresentationSteps(trace, [], [], []);
    expect(steps.map((step) => [step.stage, step.observationId])).toEqual([["OBSERVATION", "obs-zero"], ["VISIBILITY", "obs-zero"], ["ROUTING", "obs-zero"], ["OBSERVATION", "obs-next"]]);
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
