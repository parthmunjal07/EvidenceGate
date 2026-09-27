import { afterEach, describe, expect, it } from "vitest";
import type { ResultDto, RuntimeTraceEvent } from "../api/types";
import { cacheReplayEvidence, cachedObservationIds, clearReplayEvidenceCache, readCachedObservation, readCachedObservations } from "./replayEvidenceCache";

const observation = {
  observation_id: "private-observation-id", observation_type: "PACKET", event_time: "2026-01-01T00:00:00Z",
  source_position: "1", wire_direction: "FORWARD", direction_basis: "CONFIGURED_NETWORK_BOUNDARY", finality: "CURRENT",
  availability_basis: "SOURCE_DECLARED", present_fields: [], identity: { observed_identifiers: [], identifier_basis: "SOURCE_DECLARED_ROLE", role_assignments: [] },
  visibility: { available: [], unavailable: [], degraded: [] }, quality: { packet_loss: "UNKNOWN", sampling: "UNKNOWN", parser: "CLEAR", capture_gap: "UNKNOWN" },
  facts: { source_address: "198.51.100.1", destination_address: "192.0.2.1", protocol_number: 6 },
};
const source = { record_number: 1, event_time: observation.event_time, observation_type: "PACKET", facts: { source_address: "198.51.100.1" } };

afterEach(() => clearReplayEvidenceCache());

describe("latest replay source context cache", () => {
  it("supports source-observation navigation without per-observation requests", () => {
    const events = [
      { kind: "SOURCE_RECORD_ACCEPTED", source_record: source },
      { kind: "OBSERVATION_CREATED", observation_id: observation.observation_id, canonical_observation: observation },
      { kind: "ROUTED", observation_id: observation.observation_id, lane_id: "ddos.syn_state" },
    ] as unknown as RuntimeTraceEvent[];
    const result = { result_id: "result-1", source_observation_ids: [observation.observation_id] } as ResultDto;
    cacheReplayEvidence(events, [result]);
    expect(cachedObservationIds([observation.observation_id, "unavailable"])).toEqual([observation.observation_id]);
    expect(readCachedObservation(observation.observation_id)).toMatchObject({ observation, source, results: [result] });
  });
  it("clears cached trace data when a new replay begins", () => {
    cacheReplayEvidence([], []);
    clearReplayEvidenceCache();
    expect(cachedObservationIds([observation.observation_id])).toEqual([]);
  });
  it("returns source observations in the Result's lineage order", () => {
    const second = { ...observation, observation_id: "observation-2", source_position: "2" };
    const events = [
      { kind: "OBSERVATION_CREATED", observation_id: second.observation_id, canonical_observation: second },
      { kind: "OBSERVATION_CREATED", observation_id: observation.observation_id, canonical_observation: observation },
    ] as unknown as RuntimeTraceEvent[];
    cacheReplayEvidence(events, []);
    expect(readCachedObservations([observation.observation_id, second.observation_id]).map((item) => item.observation_id)).toEqual([observation.observation_id, second.observation_id]);
  });
});
