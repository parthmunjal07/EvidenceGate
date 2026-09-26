import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ReplayStatusResponse } from "../api/types";
import { useEvidence } from "../state/EvidenceContext";

export function useReplay() {
  const { state, dispatch } = useEvidence();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (state.replay?.state !== "RUNNING") return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const replay = await api.replayStatus(controller.signal);
        dispatch({ type: "replay", value: replay });
        if (replay.state === "RUNNING") timer = setTimeout(poll, 400);
        else {
          const runtime = await api.runtime(controller.signal);
          dispatch({ type: "runtime", value: runtime });
        }
      } catch (e) {
        if (!controller.signal.aborted)
          setError(
            e instanceof Error ? e.message : "Replay status unavailable",
          );
      }
    };
    timer = setTimeout(poll, 0);
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [state.replay?.state, dispatch]);
  async function start(scenario: string, speed: number) {
    setBusy(true);
    setError(null);
    try {
      const replay: ReplayStatusResponse = await api.replay({
        scenario,
        speed,
      });
      dispatch({ type: "replay", value: replay });
      return replay;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Replay failed");
      return null;
    } finally {
      setBusy(false);
    }
  }
  return {
    scenarios: state.runtime?.scenarios ?? [],
    replay: state.replay,
    busy,
    error,
    start,
  };
}
