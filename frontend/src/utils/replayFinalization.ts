export type ReplayFinalizationBarrier = {
  runtimeCompleted: boolean;
  traceDrained: boolean;
  resultAttributionComplete: boolean;
  familyRequestComplete: boolean;
  investigationRequestComplete: boolean;
  demoContractValidated: boolean;
  scopedEvidenceConsistent: boolean;
};

export function replayFinalizationReady(barrier: ReplayFinalizationBarrier) {
  return Object.values(barrier).every(Boolean);
}
