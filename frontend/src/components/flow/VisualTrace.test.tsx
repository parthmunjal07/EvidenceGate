import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import type { ResultDto } from "../../api/types";
import { VisualTrace, visualTraceTiming } from "./VisualTrace";

const result = (id: string, family: string): ResultDto => ({
  result_id: id,
  created_time: "2026-09-25T00:00:00Z",
  family,
  lane_id: `${family.toLowerCase()}.test`,
  result_type: "INSUFFICIENT_EVIDENCE",
  source_observation_ids: ["observation-1"],
} as ResultDto);

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("Replay visual trace", () => {
  it("uses a bounded, narratable Demo pace distinct from Normal", () => {
    expect(visualTraceTiming.maxQueuedTraces).toBe(3);
    expect(visualTraceTiming.demoSteps.reduce((sum, time) => sum + time, 0)).toBeGreaterThanOrEqual(4000);
    expect(visualTraceTiming.demoSteps.reduce((sum, time) => sum + time, 0)).toBeLessThanOrEqual(5000);
    expect(visualTraceTiming.normalSteps.reduce((sum, time) => sum + time, 0)).toBeLessThan(2500);
  });

  it("shows separate analytics for results tied to the same source observation", () => {
    vi.useFakeTimers();
    render(<VisualTrace events={[result("r2", "DNS_TUNNELLING"), result("r1", "DGA")]} pace="demo" />);
    expect(screen.getByText("DGA · independent evidence")).toBeInTheDocument();
    expect(screen.getByText("DNS tunnelling · independent evidence")).toBeInTheDocument();
    expect(screen.getByText("Display pacing does not represent processing latency.")).toBeInTheDocument();
  });

  it("resolves immediately when reduced motion is enabled", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({ matches: query.includes("prefers-reduced-motion"), addEventListener: () => {}, removeEventListener: () => {} }));
    render(<VisualTrace events={[result("r1", "DGA")]} pace="demo" />);
    await act(async () => {});
    expect(screen.getByText("Reduced motion is enabled. Results are shown without animation.")).toBeInTheDocument();
    expect(document.querySelectorAll(".trace-stage.is-active")).toHaveLength(0);
  });
});
