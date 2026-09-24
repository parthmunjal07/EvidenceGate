import type { EvidenceAction, EvidenceState } from "./types";

export const initialEvidenceState: EvidenceState = {
  runtime: null,
  results: new Map(),
  orderedResults: [],
  alerts: [],
  statusItems: [],
  replay: null,
  nextCursor: null,
  syncCursor: null,
  pageError: null,
  streamState: "connecting",
  latestResult: null,
  replayEvents: [],
};

export function evidenceReducer(
  state: EvidenceState,
  action: EvidenceAction,
): EvidenceState {
  switch (action.type) {
    case "runtime":
      return {
        ...state,
        runtime: action.value,
        replay: action.value.replay,
        pageError: null,
      };
    case "results": {
      const results = new Map(state.results);
      const added: string[] = [];
      for (const result of action.value) {
        if (!results.has(result.result_id)) added.push(result.result_id);
        results.set(result.result_id, result);
      }
      const orderedResults = [
        ...new Set([...added, ...state.orderedResults]),
      ].sort((a, b) => {
        const left = results.get(a)!;
        const right = results.get(b)!;
        return (
          right.created_time.localeCompare(left.created_time) ||
          right.result_id.localeCompare(left.result_id)
        );
      });
      const fresh = action.animate
        ? action.value.filter((item) => added.includes(item.result_id))
        : [];
      return {
        ...state,
        results,
        orderedResults,
        nextCursor:
          action.cursor === undefined ? state.nextCursor : action.cursor,
        syncCursor:
          action.syncCursor === undefined
            ? state.syncCursor
            : action.syncCursor,
        latestResult: fresh[0] ?? state.latestResult,
        replayEvents: [...fresh, ...state.replayEvents].slice(0, 8),
        pageError: null,
      };
    }
    case "alerts":
      return {
        ...state,
        alerts: action.value.alerts,
        statusItems: action.value.status_items,
        pageError: null,
      };
    case "replay":
      return { ...state, replay: action.value };
    case "error":
      return { ...state, pageError: action.value };
    case "stream":
      return { ...state, streamState: action.value };
  }
}
