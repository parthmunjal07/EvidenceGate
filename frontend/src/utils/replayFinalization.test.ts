import { describe, expect, it } from "vitest";
import {
  replayFinalizationReady,
  type ReplayFinalizationBarrier,
} from "./replayFinalization";

const readyBarrier: ReplayFinalizationBarrier = {
  runtimeCompleted: true,
  traceDrained: true,
  resultAttributionComplete: true,
  familyRequestComplete: true,
  investigationRequestComplete: true,
  demoContractValidated: true,
  scopedEvidenceConsistent: true,
};

describe("replay finalization barrier", () => {
  it("opens only after runtime, trace, results, family, relations, and contract are complete", () => {
    expect(replayFinalizationReady(readyBarrier)).toBe(true);
    for (const key of Object.keys(
      readyBarrier,
    ) as (keyof ReplayFinalizationBarrier)[]) {
      expect(
        replayFinalizationReady({ ...readyBarrier, [key]: false }),
        key,
      ).toBe(false);
    }
  });
});
