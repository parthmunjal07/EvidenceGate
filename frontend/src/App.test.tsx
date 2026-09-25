import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import App from "./App";

const replay = {
  state: "IDLE",
  scenario: null,
  source_type: null,
  records_read: 0,
  observations_emitted: 0,
  results_persisted: 0,
  elapsed_wall_seconds: 0,
  started_at: null,
  finished_at: null,
  error: null,
};
const runtime = {
  state: "ONLINE",
  default_target_count: 16,
  active_lane_ids: ["dga.m1"],
  targets: [
    ...["syn_state", "udp_demand", "reflection_victim", "source_diversity", "icmp_demand", "fragment_demand", "connection_churn"].map((name, i) => ({ lane_id: `ddos.${name}`, mechanism_id: ["DDOS-A-B0", "DDOS-B-B0", "DDOS-CV-B0", "DDOS-D-B0", "DDOS-E1-B0", "DDOS-E2-B0", "DDOS-E3-B0"][i], implementation: "ACTIVE_FACTUAL_MECHANISM" as const })),
    { lane_id: "c2.beacon", mechanism_id: "C2-A1-R1", implementation: "ACTIVE_FACTUAL_MECHANISM" as const },
    { lane_id: "dga.m1", mechanism_id: "DGA-A1-M1", implementation: "ACTIVE_LEXICAL_MODEL_LANE" as const },
    { lane_id: "dns_tunnelling.t1", mechanism_id: "DNS-T1", implementation: "ACTIVE_FACTUAL_MECHANISM" as const },
    { lane_id: "encrypted_session.a1", mechanism_id: "ENC-A1", implementation: "ACTIVE_FACTUAL_MECHANISM" as const },
    ...["scan", "probe", "fanout", "sweep"].map((name) => ({ lane_id: `recon.${name}`, mechanism_id: `RECON-${name.toUpperCase()}`, implementation: "ACTIVE_FACTUAL_MECHANISM" as const })),
    { lane_id: "unusual_transfer.m1", mechanism_id: "EXFIL-M1", implementation: "ACTIVE_FACTUAL_MECHANISM" as const },
  ],
  family_status: [],
  database_status: "connected",
  durable_result_count: 0,
  live_subscriber_count: 0,
  replay,
  scenarios: [
    {
      id: "dns_observation",
      label: "DNS observation",
      family: "DNS Tunnelling",
      source_type: "NDJSON",
    },
  ],
  supported_sources: ["TYPED_NDJSON_REPLAY"],
  dga_model_readiness: "VERIFIED_READY",
  dga_model_failure_reason: null,
  alert_projection_available: true,
  alert_policy_active: true,
  alert_policy_version: "SIH_ALERT_POLICY_V1",
};
const alerts = {
  policy_version: "SIH_ALERT_POLICY_V1",
  policy_status: "ACTIVE",
  meaning_of_alert: "ANALYST_ATTENTION_RECORD",
  alerts: [],
  status_items: [{
    status_id: "status-1", schema_version: "1.0", policy_version: "SIH_ALERT_POLICY_V1",
    timestamp: "2026-09-25T00:00:00Z", entity_or_flow_reference: '["192.0.2.10","service/https",6,"198.51.100.10",50000]',
    mechanism_id: "DDOS-A-B0", result_type: "INSUFFICIENT_EVIDENCE", status_kind: "EVIDENCE_STATUS", priority: "INFO",
    supporting_evidence: { structured: { hidden: "raw evidence" }, evidence_items: [], source_observation_ids: [] },
    missing_prerequisites: ["reverse_tcp_state"], source_result_ids: ["2f6ba7c1-bbbb-4c4d-9a11-32a6326e326e"],
    visibility: { available: [], unavailable: ["REVERSE_TCP_STATE"], degraded: [] },
    quality: { packet_loss: "UNKNOWN", sampling: "UNKNOWN", parser: "UNKNOWN", capture_gap: "UNKNOWN" },
    claim_ceiling: "NO_ATTACK_CLAIM", governing_ids: [], provenance_refs: [], quality_refs: [], parser_refs: [],
  }],
};

class MockEventSource {
  static current: MockEventSource | null = null;
  onerror: (() => void) | null = null;
  listeners = new Map<string, (event: Event) => void>();
  constructor() {
    MockEventSource.current = this;
  }
  addEventListener(type: string, listener: EventListenerOrEventListenerObject) {
    if (typeof listener === "function") this.listeners.set(type, listener);
  }
  emit(type: string, data = "{}") {
    this.listeners.get(type)?.(new MessageEvent(type, { data }));
  }
  close() {}
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  MockEventSource.current = null;
  window.history.replaceState(null, "", "/");
});

function mockBackend() {
  vi.stubGlobal("EventSource", MockEventSource);
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), window.location.href);
      const body =
        url.pathname === "/health"
          ? { status: "ok", database: "connected" }
          : url.pathname === "/runtime"
            ? runtime
            : url.pathname === "/alerts"
              ? alerts
              : url.pathname === "/replay/status"
                ? replay
                : url.pathname === "/replay"
                  ? replay
                  : url.pathname === "/results/r-1"
                    ? {
                        result_id: "r-1",
                        created_time: "2026-09-25T00:00:00Z",
                        lane_id: "dga.m1",
                        family: "DGA",
                        result_type: "REVIEW_FINDING",
                      }
                    : {
                        results: [],
                        next_cursor: null,
                        sync_cursor:
                          url.searchParams.get("cursor") ?? "after.seed",
                      };
      void init;
      return { ok: true, status: 200, json: async () => body } as Response;
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("scrollTo", vi.fn());
  return fetchMock;
}

describe("operator console shell and live data presentation", () => {
  it("loads runtime, keeps hash navigation and marks the active section", async () => {
    mockBackend();
    render(<App />);
    const replayLink = await screen.findByRole("button", { name: /Replay/ });
    fireEvent.click(replayLink);
    expect(
      await screen.findByRole("heading", { name: "Choose a scenario" }),
    ).toBeInTheDocument();
    expect(window.location.hash).toBe("#/replay");
    expect(replayLink).toHaveAttribute("aria-current", "page");
  });
  it("renders family summaries and expands runtime mechanisms on demand", async () => {
    const fetchMock = mockBackend();
    render(<App />);
    fireEvent.click(
      await screen.findByRole("button", { name: "System status" }),
    );
    expect(await screen.findByText("7 families · 16 mechanisms")).toBeInTheDocument();
    expect(screen.getByText("C2 beaconing")).toBeInTheDocument();
    expect(screen.getByText("Model ready")).toBeInTheDocument();
    expect(screen.queryByText("ddos.syn_state")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /DDoS.*7 mechanisms/ }));
    expect(screen.getByText("ddos.syn_state")).toBeInTheDocument();
    expect(screen.getAllByText("Factual evidence")).toHaveLength(7);
    expect(screen.getByText("1 record")).toBeInTheDocument();
    expect(screen.getByText("Insufficient evidence")).toBeInTheDocument();
    expect(screen.getByText("Missing: Reverse TCP state")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Insufficient evidence/ }));
    expect(screen.queryByText(/raw evidence/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Technical details"));
    const technicalDetails = [...document.querySelectorAll<HTMLDetailsElement>(".inspector .technical-details")].find((item) => item.querySelector("summary")?.textContent === "Technical details")!;
    technicalDetails.open = true;
    fireEvent(technicalDetails, new Event("toggle"));
    expect(screen.getByText(/raw evidence/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View 2f6ba7…e326e →" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Replay" }));
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "DNS observation" }),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText("dns_observation")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Run replay" }),
    ).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([input]) => String(input) === "/runtime"),
    ).toBe(true);
    expect(
      fetchMock.mock.calls.some(([input]) =>
        String(input).startsWith("/results"),
      ),
    ).toBe(true);
    expect(
      fetchMock.mock.calls.some(([input]) => String(input) === "/alerts"),
    ).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Run replay" }));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([input]) => String(input) === "/replay"),
      ).toBe(true),
    );
    const replayCall = fetchMock.mock.calls.find(
      ([input]) => String(input) === "/replay",
    );
    expect(JSON.parse(String(replayCall?.[1]?.body))).toEqual({
      scenario: "dns_observation",
      speed: 0,
    });
  });
  it("fetches the durable Result record after an SSE notification", async () => {
    const fetchMock = mockBackend();
    render(<App />);
    await waitFor(() => expect(MockEventSource.current).not.toBeNull());
    MockEventSource.current?.emit(
      "result",
      JSON.stringify({
        event: "result",
        result_id: "r-1",
        cursor: "after.next",
      }),
    );
    expect(
      await screen.findByText("Latest persisted result: DGA · dga.m1"),
    ).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([input]) => String(input) === "/results/r-1"),
    ).toBe(true);
  });
  it("resynchronizes durable results from the last cursor on stream gap", async () => {
    const fetchMock = mockBackend();
    render(<App />);
    await waitFor(() => expect(MockEventSource.current).not.toBeNull());
    MockEventSource.current?.emit("stream_gap");
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([input]) => {
          const url = new URL(String(input), window.location.href);
          return (
            url.pathname === "/results" &&
            url.searchParams.get("cursor") === "after.seed"
          );
        }),
      ).toBe(true),
    );
  });
  it("shows a meaningful message when the backend is unavailable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 503,
        json: async () => ({ detail: "Database is not connected" }),
      })),
    );
    vi.stubGlobal("scrollTo", vi.fn());
    render(<App />);
    expect(
      await screen.findByText("Database is not connected"),
    ).toBeInTheDocument();
    expect(screen.getByText("Offline")).toBeInTheDocument();
  });
  it("puts recent alerts before the live path and offers replay when empty", async () => {
    mockBackend();
    render(<App />);
    const alertsHeading = await screen.findByRole("heading", { name: "Recent alerts" });
    const flowHeading = screen.getByRole("heading", { name: "Live evidence path" });
    expect(alertsHeading.compareDocumentPosition(flowHeading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByRole("button", { name: /Run a replay/ })).toBeInTheDocument();
  });
  it("keeps the analyst review caveat and source-result relationship visible", async () => {
    mockBackend();
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Analyst alerts/ }));
    expect(screen.getByText("Alert means analyst review, not confirmation of malicious activity.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Evidence results" }));
    expect(screen.getByText("Evidence results are the source records behind analyst alerts.")).toBeInTheDocument();
  });
});
