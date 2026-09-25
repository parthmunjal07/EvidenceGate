import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import type { ResultDto } from "../../api/types";
import { VisualTrace, visualTraceTiming } from "./VisualTrace";

const result = (id: string, family: string): ResultDto => ({
  result_id: id, created_time: "2026-09-25T00:00:00Z", family,
  lane_id: family === "DGA" ? "dga.m1" : "dns_tunnelling.t1",
  mechanism_id: family === "DGA" ? "DGA-A1-M1" : "DNS-T1", result_type: "REVIEW_FINDING",
  source_observation_ids: ["observation-1"],
} as ResultDto);
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });
describe("processing trace", () => {
  it("uses a bounded presentation pace distinct from replay rate", () => {
    expect(visualTraceTiming.maxQueuedTraces).toBe(3);
    expect(visualTraceTiming.demoSteps.reduce((sum, time) => sum + time, 0)).toBeGreaterThanOrEqual(4000);
    expect(visualTraceTiming.demoSteps.reduce((sum, time) => sum + time, 0)).toBeLessThanOrEqual(5000);
    expect(visualTraceTiming.normalSteps.reduce((sum, time) => sum + time, 0)).toBeLessThan(2500);
  });
  it("shows branches for results linked to the same source observation", () => {
    vi.useFakeTimers();
    render(<VisualTrace events={[result("r2", "DNS_TUNNELLING"), result("r1", "DGA")]} pace="demo" />);
    expect(screen.getByText("DGA → DGA lexical evidence → Evidence")).toBeInTheDocument();
    expect(screen.getByText("DNS tunnelling → DNS name structure → Evidence")).toBeInTheDocument();
    expect(screen.getByText(/display pacing does not represent processing latency/i)).toBeInTheDocument();
  });
  it("shows the completed path immediately when reduced motion is enabled", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({ matches: query.includes("prefers-reduced-motion"), addEventListener: () => {}, removeEventListener: () => {} }));
    render(<VisualTrace events={[result("r1", "DGA")]} pace="demo" />);
    await act(async () => {});
    expect(screen.getByText("DGA → DGA lexical evidence → Evidence")).toBeInTheDocument();
    expect(document.querySelectorAll(".trace-stage.is-active")).toHaveLength(5);
  });
});
