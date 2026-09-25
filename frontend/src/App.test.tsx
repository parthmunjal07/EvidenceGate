import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "./App";

const replay = { state: "IDLE", scenario: null, source_type: null, records_read: 0, observations_emitted: 0, results_persisted: 0, elapsed_wall_seconds: 0, started_at: null, finished_at: null, error: null };
const runtime = {
  state: "ONLINE", default_target_count: 16, active_lane_ids: ["ddos.reflection_victim", "dga.m1"],
  targets: [{ lane_id: "ddos.reflection_victim", mechanism_id: "DDOS-CV-B0", implementation: "ACTIVE_FACTUAL_MECHANISM" }, { lane_id: "dga.m1", mechanism_id: "DGA-A1-M1", implementation: "ACTIVE_LEXICAL_MODEL_LANE" }],
  family_status: [{ family: "ddos", status: "ACTIVE" }], database_status: "connected", durable_result_count: 1, live_subscriber_count: 0, replay,
  scenarios: [{ id: "mixed_ddos_recon", label: "DDoS and reconnaissance", family: "DDoS", source_type: "NDJSON" }, { id: "raw_pcap_ddos_recon", label: "Recorded DDoS traffic", family: "DDoS", source_type: "PCAP" }],
  supported_sources: ["TYPED_NDJSON_REPLAY", "PCAP"], dga_model_readiness: "ARTIFACT_MISSING", dga_model_failure_reason: "ARTIFACT_MISSING", alert_projection_available: true, alert_policy_active: true, alert_policy_version: "SIH_ALERT_POLICY_V1",
};
const alert = {
  alert_id: "alert-1", schema_version: "1", policy_version: "SIH_ALERT_POLICY_V1", timestamp: "2026-09-25T00:00:00Z", entity_or_flow_reference: "192.0.2.10", threat_class: "DOS", mechanism_id: "DDOS-CV-B0", result_type: "REVIEW_FINDING", severity: "REVIEW", confidence_score: null, confidence_basis: "OBSERVED_EVIDENCE", confidence_statement: "Observed evidence",
  supporting_evidence: { structured: { bytes_c2s_per_second: 409.6 }, evidence_items: [], source_observation_ids: ["obs-1"] }, source_result_ids: ["result-1"], visibility: { available: ["PACKET_FACTS"], unavailable: [], degraded: [] }, quality: { packet_loss: "UNKNOWN", sampling: "UNKNOWN", parser: "UNKNOWN", capture_gap: "UNKNOWN" }, claim_ceiling: "RESPONSE_SHAPED_TRAFFIC_ONLY;NO_AMPLIFICATION_RATIO;NO_SPOOFING_CONFIRMED;NO_DDOS_CONFIRMED;NO_ATTACKER_IDENTITY", model_refs: [], governing_ids: [], provenance_refs: [], quality_refs: [], parser_refs: [],
};
const alerts = { policy_version: "SIH_ALERT_POLICY_V1", policy_status: "ACTIVE", meaning_of_alert: "ANALYST_ATTENTION_RECORD", alerts: [alert], status_items: [] };
class MockEventSource {
  static current: MockEventSource | null = null;
  listeners = new Map<string, (event: Event) => void>();
  constructor() { MockEventSource.current = this; }
  addEventListener(type: string, listener: EventListenerOrEventListenerObject) { if (typeof listener === "function") this.listeners.set(type, listener); }
  emit(type: string, data = "{}") { this.listeners.get(type)?.(new MessageEvent(type, { data })); }
  close() {}
}
function mockBackend() {
  vi.stubGlobal("EventSource", MockEventSource);
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), window.location.href);
    const body = url.pathname === "/health" ? { status: "ok", database: "connected" } : url.pathname === "/runtime" ? runtime : url.pathname === "/alerts" ? alerts : url.pathname.startsWith("/replay") ? replay : { results: [], next_cursor: null, sync_cursor: url.searchParams.get("cursor") ?? "seed" };
    void init;
    return { ok: true, status: 200, json: async () => body } as Response;
  });
  vi.stubGlobal("fetch", fetchMock); vi.stubGlobal("scrollTo", vi.fn()); return fetchMock;
}
afterEach(() => { cleanup(); vi.unstubAllGlobals(); MockEventSource.current = null; window.history.replaceState(null, "", "/"); });

describe("analyst-first console", () => {
  it("uses the final primary navigation and hides the system status page", async () => {
    mockBackend(); render(<App />);
    expect(await screen.findByRole("button", { name: "Overview" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Analyst queue/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Evidence" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Traffic lab" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "System status" })).not.toBeInTheDocument();
    expect(screen.queryByText("SIH_ALERT_POLICY_V1")).not.toBeInTheDocument();
    expect(screen.queryByText("Evidence flow")).not.toBeInTheDocument();
  });
  it("shows runtime online separately from a missing DGA capability and exposes diagnostics on demand", async () => {
    mockBackend(); render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Online" }));
    expect(screen.getByRole("dialog", { name: "System health" })).toBeInTheDocument();
    expect(screen.getByText("DGA model")).toBeInTheDocument();
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
    expect(screen.getByText("1 capability issue: DGA model unavailable.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Technical details/ }));
    expect(screen.getByRole("dialog", { name: "Technical details" })).toBeInTheDocument();
    expect(screen.getByText(/DDOS-CV-B0/)).toBeInTheDocument();
    expect(screen.getByText("SIH_ALERT_POLICY_V1")).toBeInTheDocument();
  });
  it("answers why an item surfaced without exposing IDs in the queue", async () => {
    mockBackend(); render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Analyst queue/ }));
    expect(screen.getByText("Why surfaced")).toBeInTheDocument();
    expect(screen.getByText(/Response-shaped traffic was observed for this peer/)).toBeInTheDocument();
    expect(screen.queryByText("DDOS-CV-B0")).not.toBeInTheDocument();
    fireEvent.click(screen.getAllByText(/Response-shaped traffic was observed for this peer/)[0]!);
    expect(screen.getByText("What this evidence supports")).toBeInTheDocument();
    expect(screen.getByText("Response-shaped traffic was observed.")).toBeInTheDocument();
    expect(screen.getByText(/An amplification ratio is not established/)).toBeInTheDocument();
    expect(screen.getByText(alert.claim_ceiling).closest("details")).not.toHaveAttribute("open");
    fireEvent.click(screen.getByText("Technical details"));
    expect(screen.getByText(alert.claim_ceiling)).toBeInTheDocument();
  });
  it("keeps Traffic lab factual and moves the trace into an on-demand modal", async () => {
    const fetchMock = mockBackend(); render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Traffic lab" }));
    expect(screen.getByText(/does not simulate a live network/)).toBeInTheDocument();
    expect(screen.queryByText("mixed_ddos_recon")).not.toBeInTheDocument();
    expect(screen.queryByText("Visual pace")).not.toBeInTheDocument();
    expect(screen.queryByText("Processing trace")).not.toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: /Run scenario/ })[0]!);
    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => String(input) === "/replay")).toBe(true));
    expect(JSON.parse(String(fetchMock.mock.calls.find(([input]) => String(input) === "/replay")?.[1]?.body))).toEqual({ scenario: "mixed_ddos_recon", speed: 0 });
  });
});
