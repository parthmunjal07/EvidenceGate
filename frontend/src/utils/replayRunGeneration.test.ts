import { describe, expect, it } from "vitest";
import { ReplayRunGeneration } from "./replayRunGeneration";

describe("replay run generation", () => {
  it("rejects a late response from a prior run after a new run begins", () => {
    const runs = new ReplayRunGeneration();
    const first = runs.begin();
    const second = runs.begin();

    expect(runs.isCurrent(first)).toBe(false);
    expect(runs.isCurrent(second)).toBe(true);
  });
});
