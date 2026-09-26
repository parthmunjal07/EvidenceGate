import { describe, expect, it } from "vitest";
import type { FamilyEvidenceViewDto, InvestigationLinkDto, ReplayStatusResponse, ResultDto, RuntimeTraceEvent } from "../api/types";
import { completeTraceRange, filterLatestReplayEvidence, replayMarkerMatches, type LatestReplayMarker } from "./latestReplayScope";

const result = (id: string, family: string, observations: string[]) => ({ result_id: id, family, source_observation_ids: observations } as ResultDto);
const view = (id: string, family: string, resultId: string) => ({ family_view_id: id, family, source_result_ids: [resultId] } as FamilyEvidenceViewDto);
const trace = (sequence: number, observationId: string): RuntimeTraceEvent => ({ sequence, kind: "OBSERVATION_CREATED", occurred_at: "2026-01-01T00:00:00Z", observation_id: observationId, observation_type: "PACKET", lane_id: null, mechanism: null, readiness: null, reason: null, result_id: null, source_observation_ids: [] });
const marker: LatestReplayMarker = { scenario: "mixed_ddos_recon", sourceType: "PCAP", startedAt: "2026-01-01T00:00:00Z", finishedAt: "2026-01-01T00:00:01Z", startSequence: 10, endSequence: 11 };

describe("latest replay evidence scope", () => {
  it("shows only family views and links supported by source-observation lineage", () => {
    const results = [result("r-ddos", "DDoS", ["obs-latest"]), result("r-recon", "Reconnaissance", ["obs-latest"]), result("r-dga", "DGA + DNS", ["obs-old"] )];
    const views = [view("v-ddos", "DDoS", "r-ddos"), view("v-recon", "Reconnaissance", "r-recon"), view("v-dga", "DGA + DNS", "r-dga")];
    const links = [
      { link_id: "l-current", left_family_view_id: "v-ddos", right_family_view_id: "v-recon", source_result_ids: ["r-ddos", "r-recon"] },
      { link_id: "l-old", left_family_view_id: "v-recon", right_family_view_id: "v-dga", source_result_ids: ["r-dga"] },
    ] as InvestigationLinkDto[];
    const latest = filterLatestReplayEvidence(results, [trace(11, "obs-latest")], views, links);
    const retained = filterLatestReplayEvidence(results, [trace(11, "obs-latest"), trace(12, "obs-old")], views, links);
    expect(latest.results.map((item) => item.family).sort()).toEqual(["DDoS", "Reconnaissance"]);
    expect(latest.views.map((item) => item.family).sort()).toEqual(["DDoS", "Reconnaissance"]);
    expect(latest.links.map((item) => item.link_id)).toEqual(["l-current"]);
    expect(retained.views).toHaveLength(3);
    expect(retained.links).toHaveLength(2);
  });

  it("rejects a missing trace sequence and verifies the completed replay marker", () => {
    expect(completeTraceRange([trace(11, "obs-latest")], marker, 11)).toBe(true);
    expect(completeTraceRange([], marker, 11)).toBe(false);
    expect(completeTraceRange([trace(12, "obs-latest")], marker, 12)).toBe(false);
    const replay = { state: "COMPLETED", scenario: marker.scenario, source_type: marker.sourceType, started_at: marker.startedAt, finished_at: marker.finishedAt } as ReplayStatusResponse;
    expect(replayMarkerMatches(marker, replay)).toBe(true);
    expect(replayMarkerMatches({ ...marker, startedAt: "2026-01-02T00:00:00Z" }, replay)).toBe(false);
  });
});
