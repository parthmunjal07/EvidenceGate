import { useState } from "react";
import { useEvidence } from "../state/EvidenceContext";
import { PageHeading, EmptyState } from "../components/common/Primitives";
import { formatShortTime, readable } from "../utils/formatting";
import { useReplay } from "../hooks/useReplay";
import type { PageKey } from "../state/types";

export function ReplayPage({
  navigate,
}: {
  navigate: (page: PageKey) => void;
}) {
  const { state } = useEvidence();
  const { scenarios, replay, error, start, busy } = useReplay();
  const [speed, setSpeed] = useState(0);
  const running = replay?.state === "RUNNING";
  return (
    <section className="page active-page" aria-labelledby="replay-title">
      <PageHeading
        titleId="replay-title"
        title="Replay"
        deck="Run a controlled scenario through passive analysis."
      />
      <div className="replay-intro">
        <div className="replay-intro-mark">▷</div>
        <div>
          <h2>About replay</h2>
          <p>
            Replay uses scenarios made available by the runtime. One observation
            can produce evidence for more than one analytic. Results appear in
            Evidence results and the live evidence path.
          </p>
        </div>
      </div>
      <section className="panel replay-run-panel">
        <div className="panel-head compact">
          <div>
            <h2>Choose a scenario</h2>
          </div>
          <label className="speed-control">
            Replay speed
            <select
              value={speed}
              onChange={(event) => setSpeed(Number(event.target.value))}
            >
              <option value={0}>Unpaced</option>
              <option value={0.5}>0.5× event-time spacing</option>
              <option value={1}>1× event-time spacing</option>
              <option value={2}>2× event-time spacing</option>
            </select>
          </label>
        </div>
        <div className="scenario-grid">
          {scenarios.map((scenario) => (
            <article className="scenario-card" key={scenario.id}>
              <div className="scenario-title">
                <span className="scenario-icon">▷</span>
                <div>
                  <h3>{scenario.label}</h3>
                  <p>
                    {scenario.family} · {scenario.source_type}
                  </p>
                </div>
              </div>
              <code className="scenario-id">{scenario.id}</code>
              <button
                className="primary-button run-replay"
                disabled={running || busy}
                onClick={() => void start(scenario.id, speed)}
              >
                {running
                  ? "Replay running…"
                  : busy
                    ? "Starting replay…"
                    : "Run replay"}
              </button>
            </article>
          ))}
          {!scenarios.length && (
            <EmptyState>
              No allowlisted replay scenarios are available.
            </EmptyState>
          )}
        </div>
      </section>
      <section className="panel replay-progress-panel">
        <div className="panel-head compact">
          <div>
            <h2>
              {running
                ? `Replaying ${replay.scenario}`
                : replay?.state === "FAILED"
                  ? "Replay failed"
                  : replay?.state === "COMPLETED"
                    ? `Completed ${replay.scenario}`
                    : "No replay is running"}
            </h2>
          </div>
          <span
            className={`status-chip${running ? " running" : replay?.state === "FAILED" ? " warning" : " neutral"}`}
          >
            {replay?.state === "RUNNING" ? "Replaying" : replay?.state === "COMPLETED" ? "Completed" : replay?.state === "FAILED" ? "Failed" : "Idle"}
          </span>
        </div>
        <div className="progress-track">
          <div
            className={running ? "indeterminate" : ""}
            style={{
              width: running
                ? "35%"
                : replay?.state === "COMPLETED"
                  ? "100%"
                  : "0%",
            }}
          />
        </div>
        {replay && (
          <div className="replay-counters">
            {[
              ["Source", replay.source_type || "—"],
              ["Records read", replay.records_read],
              ["Observations emitted", replay.observations_emitted],
              ["Results persisted", replay.results_persisted],
              ["Elapsed", `${replay.elapsed_wall_seconds.toFixed(2)} s`],
            ].map(([label, value]) => (
              <div key={String(label)}>
                <span className="field-label">{label}</span>
                <strong>{value}</strong>
              </div>
            ))}
          </div>
        )}
        <div className="replay-message" role="status">
          {error ||
            replay?.error ||
            (running
              ? "Replay is processing source records. Persisted results will appear as they arrive."
              : replay?.state === "COMPLETED"
                ? `Replay finished at ${replay.finished_at || "—"}. Results remain available in Evidence results.`
                : "Select an allowlisted scenario to begin.")}
        </div>
      </section>
      <section className="panel replay-flow-panel">
        <div className="panel-head compact">
          <div>
            <h2>Replay results</h2>
          </div>
          <button className="text-button" onClick={() => navigate("overview")}>
            View overview →
          </button>
        </div>
        <div className="replay-event-log">
          {state.replayEvents.length ? (
            state.replayEvents.map((result) => (
              <div className="event-log-item" key={result.result_id}>
                <time>{formatShortTime(result.created_time)}</time>
                <strong>{result.lane_id}</strong>
                <span>
                  {readable(result.result_type)} ·{" "}
                  {result.mechanism_id || result.lane_id}
                </span>
              </div>
            ))
          ) : (
            <span className="log-empty">
              No replay events received in this session.
            </span>
          )}
        </div>
      </section>
    </section>
  );
}
