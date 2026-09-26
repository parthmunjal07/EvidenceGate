import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  type ReactNode,
} from "react";
import { api } from "../api/client";
import type { ResultNotification } from "../api/types";
import { evidenceReducer, initialEvidenceState } from "./evidenceReducer";
import type { EvidenceAction, EvidenceState } from "./types";

type EvidenceValue = {
  state: EvidenceState;
  dispatch: (action: EvidenceAction) => void;
  loadOlder: () => Promise<void>;
  selectSourceResult: (id: string) => Promise<void>;
};
const EvidenceContext = createContext<EvidenceValue | null>(null);

export function EvidenceProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(evidenceReducer, initialEvidenceState);
  useEffect(() => {
    const controller = new AbortController();
    let source: EventSource | null = null;
    let eventQueue = Promise.resolve();
    let alertsAvailable = false;
    let syncCursor: string | null = null;
    const loadAlerts = async () => {
      if (alertsAvailable)
        dispatch({
          type: "alerts",
          value: await api.alerts(controller.signal),
        });
    };
    const resync = async () => {
      let cursor = syncCursor;
      if (!cursor) {
        const page = await api.results({ limit: 100 }, controller.signal);
        dispatch({
          type: "results",
          value: page.results,
          cursor: page.next_cursor,
          syncCursor: page.sync_cursor,
        });
        syncCursor = page.sync_cursor;
      } else {
        for (;;) {
          const page = await api.results(
            { limit: 500, cursor },
            controller.signal,
          );
          dispatch({
            type: "results",
            value: page.results,
            syncCursor: page.sync_cursor,
            animate: true,
          });
          syncCursor = page.sync_cursor ?? syncCursor;
          if (!page.next_cursor) break;
          cursor = page.next_cursor;
        }
      }
      await loadAlerts();
    };
    void (async () => {
      try {
        const [health, runtime] = await Promise.all([
          api.health(controller.signal),
          api.runtime(controller.signal),
        ]);
        if (health.status !== "ok") throw new Error("Backend unavailable");
        alertsAvailable = runtime.alert_projection_available;
        dispatch({ type: "runtime", value: runtime });
        dispatch({ type: "replay", value: runtime.replay });
        await resync();
        source = new EventSource("/events");
        source.addEventListener("ready", () => {
          dispatch({ type: "stream", value: "connected" });
          eventQueue = eventQueue.then(resync).catch(showError);
        });
        source.addEventListener("result", (event) => {
          eventQueue = eventQueue
            .then(async () => {
              const message = JSON.parse(
                (event as MessageEvent<string>).data,
              ) as ResultNotification;
              // SSE is only a persisted-result hint. Fetch the durable scientific record from REST.
              const result = await api.result(
                message.result_id,
                controller.signal,
              );
              syncCursor = message.cursor;
              dispatch({
                type: "results",
                value: [result],
                syncCursor: message.cursor,
                animate: true,
              });
              await loadAlerts();
            })
            .catch(showError);
        });
        source.addEventListener("stream_gap", () => {
          dispatch({ type: "stream", value: "reconnecting" });
          eventQueue = eventQueue.then(resync).catch(showError);
        });
        source.onerror = () =>
          dispatch({ type: "stream", value: "reconnecting" });
      } catch (error) {
        showError(error);
      }
    })();
    function showError(error: unknown) {
      if (!controller.signal.aborted)
        dispatch({
          type: "error",
          value: error instanceof Error ? error.message : "Request failed",
        });
    }
    return () => {
      controller.abort();
      source?.close();
    };
    // Initial bootstrap owns the stream lifecycle; later state changes do not reopen EventSource.
  }, []);

  const value = useMemo<EvidenceValue>(
    () => ({
      state,
      dispatch,
      loadOlder: async () => {
        if (!state.nextCursor) return;
        const page = await api.results({
          limit: 100,
          cursor: state.nextCursor,
        });
        dispatch({
          type: "results",
          value: page.results,
          cursor: page.next_cursor,
        });
      },
      selectSourceResult: async (id) => {
        if (state.results.has(id)) return;
        const result = await api.result(id);
        dispatch({ type: "results", value: [result] });
      },
    }),
    [state],
  );
  return (
    <EvidenceContext.Provider value={value}>
      {children}
    </EvidenceContext.Provider>
  );
}

export function useEvidence() {
  const value = useContext(EvidenceContext);
  if (!value)
    throw new Error("useEvidence must be used inside EvidenceProvider");
  return value;
}
