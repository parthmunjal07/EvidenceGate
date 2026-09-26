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
const familyView = { family_view_id: "family-1", family: "DDoS", time_start: "2026-09-25T00:00:00Z", time_end: "2026-09-25T00:00:00Z", entity_references: ["192.0.2.10"], source_result_ids: ["result-1"], source_observation_ids: ["obs-1"], findings: [{ source_result_id: "result-1", title: "Reflection-shaped traffic", statements: ["Response-shaped traffic was observed.", "state:provider.ddos.example:[\"192.0.2.10\"]"], result_type: "REVIEW_FINDING" }, { source_result_id: "result-2", title: "Reflection-shaped traffic", statements: ["Initiating TCP attempts were measured."], result_type: "REVIEW_FINDING" }], limitations: ["This evidence does not confirm an attack."], missing_evidence: ["Reverse TCP state was not visible."], visibility_summary: [], quality_summary: ["parser:CLEAR", "parser:UNKNOWN"] };
const resultDto = { result_id: "result-1", schema_version: "3", result_type: "REVIEW_FINDING", created_time: "2026-09-25T00:00:00Z", lane_id: "ddos.reflection_victim", family: "DDoS", plugin_id: "ddos", plugin_version: "1", analytic_version: "1", governance_version: "1", entity_reference: "192.0.2.10", taxonomy: ["DOS", "DDoS", "evidence"], mechanism_id: "DDOS-CV-B0", status_snapshot: { scientific_status: "EVIDENCE_CONSTRUCTION", integration_status: "BASELINE_IMPLEMENTED", governance_version: "1", readiness: "READY", quality_degraded: false }, claim_ceiling: "RESPONSE_SHAPED_TRAFFIC_ONLY;NO_DDOS_CONFIRMED", evidence: { evidence_kind: "RESPONSE_SHAPED_TRAFFIC" }, evidence_items: [], missing_prerequisites: [], source_observation_ids: ["obs-1"], source_ids: [], quality_snapshot: { packet_loss: "CLEAR", sampling: "CLEAR", parser: "CLEAR", capture_gap: "CLEAR" }, visibility_snapshot: { available: ["PACKET_FACTS"], unavailable: [], degraded: [] }, state_version: null, config_hash: null, parser_refs: [], model_refs: [], governing_ids: [], quality_refs: [], provenance_refs: [], evidence_interval: null, reason_code: null };
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
    const body = url.pathname === "/health" ? { status: "ok", database: "connected" } : url.pathname === "/runtime" ? runtime : url.pathname === "/alerts" ? alerts : url.pathname === "/family-evidence" ? { family_views: [familyView] } : url.pathname === "/investigations" ? { family_views: [familyView], links: [] } : url.pathname.startsWith("/replay") ? replay : url.pathname === "/results/result-1" ? resultDto : { results: [resultDto], next_cursor: null, sync_cursor: url.searchParams.get("cursor") ?? "seed" };
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
    expect(screen.getByRole("button", { name: /Analyst queue/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Evidence" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Traffic Lab" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Investigations" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "System status" })).not.toBeInTheDocument();
    expect(screen.queryByText("SIH_ALERT_POLICY_V1")).not.toBeInTheDocument();
    expect(screen.queryByText("Evidence flow")).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/(?:\u00C3|\u00C2|\u00E2\u2020|\uFFFD)/);
  });
  it("restores a contextual page from a URL hash with query parameters", async () => {
    window.history.replaceState(null, "", "#/investigations?link_id=investigation-1");
    mockBackend(); render(<App />);
    expect(await screen.findByRole("heading", { name: "Investigations" })).toBeInTheDocument();
  });
  it("leads with evidence posture and keeps runtime measurements behind a disclosure", async () => {
    mockBackend(); render(<App />);
    expect(await screen.findByText("Evidence requiring review")).toBeInTheDocument();
    expect(screen.getByText("Threat-family posture")).toBeInTheDocument();
    expect(screen.getByText("DGA + DNS")).toBeInTheDocument();
    expect(screen.getByText("Needs review")).toBeInTheDocument();
    expect(screen.getByText("Evidence health")).toBeInTheDocument();
    expect(screen.queryByText("Controlled benchmark")).not.toBeInTheDocument();
    expect(screen.queryByText("Not currently instrumented")).not.toBeInTheDocument();
    expect(screen.queryByText("Not exposed")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText(/System performance · Controlled benchmark/));
    expect(screen.getByText(/Controlled benchmark: 50 observations\/s/)).toBeInTheDocument();
    expect(screen.getByText("Benchmark measurements").closest("details")).not.toHaveAttribute("open");
  });
  it("shows runtime status without a global capability issue badge and exposes diagnostics on demand", async () => {
    mockBackend(); render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Online" }));
    expect(screen.getByRole("dialog", { name: "System health" })).toBeInTheDocument();
    expect(screen.queryByText("DGA model")).not.toBeInTheDocument();
    expect(screen.queryByText(/capability issue/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Technical details/ }));
    expect(screen.getByRole("dialog", { name: "Technical details" })).toBeInTheDocument();
    expect(screen.getByText(/DDOS-CV-B0/)).toBeInTheDocument();
    expect(screen.getByText("SIH_ALERT_POLICY_V1")).toBeInTheDocument();
  });
  it("shows family evidence and an analyst-first card without technical details or IDs", async () => {
    mockBackend(); render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Analyst queue/i }));
    fireEvent.click(await screen.findByRole("button", { name: /Open evidence/ }));
    expect(screen.getByRole("dialog", { name: "Family evidence episode" })).toBeInTheDocument();
    expect((await screen.findAllByText("DDoS evidence")).length).toBeGreaterThan(0);
    expect(screen.getByText("2 independent findings")).toBeInTheDocument();
    expect(screen.getByText("2 source Results")).toBeInTheDocument();
    expect(screen.getAllByText("Reflection-shaped traffic")[0]?.closest("details")).not.toHaveAttribute("open");
    fireEvent.click(screen.getAllByText("Reflection-shaped traffic")[0]!);
    expect(screen.getAllByRole("button", { name: /View source Result/ })).toHaveLength(2);
    expect(screen.queryByText(/state:provider/)).not.toBeInTheDocument();
    expect(screen.queryByText("Target Target 192.0.2.10")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Evidence gaps" })).toBeInTheDocument();
    expect(screen.getByText("Reverse TCP state was not visible.")).toBeInTheDocument();
    expect(screen.getByText("This evidence does not confirm an attack.")).toBeInTheDocument();
    expect(screen.getByText("Visibility and quality").closest("details")).not.toHaveAttribute("open");
    expect(screen.getByText("Show source lineage").closest("details")).not.toHaveAttribute("open");
    expect(screen.queryByText("result-1")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Open source Results/ }));
    expect(await screen.findByRole("heading", { name: "Evidence" })).toBeInTheDocument();
  });
  it("opens the dedicated factual investigation experience", async () => {
    const fetchMock = mockBackend(); render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Investigations" }));
    expect(await screen.findByText(/Chronology of separate family evidence connected by exact shared source observations/)).toBeInTheDocument();
    expect(screen.getByText("No exact shared-observation links are currently indexed.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/investigations"))).toBe(true);
  });
  it("keeps Traffic lab factual and moves the trace into an on-demand modal", async () => {
    const fetchMock = mockBackend(); render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Traffic Lab" }));
    expect(screen.getByText(/Follow controlled passive replay from source records to independent evidence/)).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /Presentation pace/ })).toHaveValue("demo");
    expect(screen.queryByText("mixed_ddos_recon")).not.toBeInTheDocument();
    expect(screen.queryByText("Visual pace")).not.toBeInTheDocument();
    expect(screen.queryByText("Processing trace")).not.toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "Run" })[0]!);
    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => String(input) === "/replay")).toBe(true));
    expect(JSON.parse(String(fetchMock.mock.calls.find(([input]) => String(input) === "/replay")?.[1]?.body))).toEqual({ scenario: "mixed_ddos_recon", speed: 0 });
  });
});
