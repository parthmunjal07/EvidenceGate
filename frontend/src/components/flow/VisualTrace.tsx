import { useEffect, useRef, useState } from "react";
import type { ResultDto } from "../../api/types";
import { useReducedMotion } from "../../hooks/useReducedMotion";
import { familyLabel, mechanismLabel } from "../../utils/formatting";

const baseStages = [
  "Controlled traffic",
  "Visibility checks",
  "Analytics",
  "Evidence",
];
const demoSteps = [600, 300, 650, 300, 700, 300, 650, 300, 650];
const normalSteps = [260, 120, 280, 120, 320, 120, 280, 120, 280];
export const visualTraceTiming = {
  demoSteps: [...demoSteps],
  normalSteps: [...normalSteps],
  maxQueuedTraces: 3,
};
const traceKey = (items: ResultDto[]) =>
  items
    .map((item) => item.result_id)
    .sort()
    .join("|");
function groupByObservation(items: ResultDto[]) {
  const groups: ResultDto[][] = [];
  for (const result of items) {
    const ids = new Set(result.source_observation_ids ?? []);
    const group = ids.size
      ? groups.find((existing) =>
          existing.some((item) =>
            (item.source_observation_ids ?? []).some((id) => ids.has(id)),
          ),
        )
      : undefined;
    if (group) group.push(result);
    else groups.push([result]);
  }
  return groups;
}

export function VisualTrace({
  events,
  pace,
}: {
  events: ResultDto[];
  pace: "demo" | "normal";
}) {
  const reduced = useReducedMotion();
  const seen = useRef(new Set<string>());
  const queue = useRef<ResultDto[][]>([]);
  const active = useRef<ResultDto[] | null>(null);
  const [current, setCurrent] = useState<ResultDto[] | null>(null);
  const [step, setStep] = useState(0);
  const [queuedCount, setQueuedCount] = useState(0);
  useEffect(() => {
    const fresh = [...events].reverse().filter((item) => {
      if (seen.current.has(item.result_id)) return false;
      seen.current.add(item.result_id);
      return true;
    });
    if (!fresh.length) return;
    const freshIds = new Set(fresh.map((item) => item.result_id));
    const groups = groupByObservation([...events].reverse()).filter((group) =>
      group.some((item) => freshIds.has(item.result_id)),
    );
    if (reduced) {
      active.current = null;
      queue.current = [];
      setCurrent(groups[0] ?? null);
      setStep(demoSteps.length - 1);
      return;
    }
    groups.forEach((group) => {
      if (active.current && traceKey(active.current) === traceKey(group))
        return;
      if (!queue.current.some((items) => traceKey(items) === traceKey(group)))
        queue.current.push(group);
    });
    queue.current = queue.current.slice(0, 3);
    setQueuedCount(queue.current.length);
    if (!active.current && queue.current.length) {
      active.current = queue.current.shift() ?? null;
      setCurrent(active.current);
      setStep(0);
    }
  }, [events, reduced]);
  useEffect(() => {
    if (!current || reduced) return;
    const steps = pace === "demo" ? demoSteps : normalSteps;
    const timer = window.setTimeout(() => {
      const nextStep = step + 1;
      if (nextStep >= steps.length) {
        active.current = null;
        const next = queue.current.shift() ?? null;
        setQueuedCount(queue.current.length);
        active.current = next;
        setCurrent(next);
        setStep(0);
      } else setStep(nextStep);
    }, steps[step] ?? 0);
    return () => window.clearTimeout(timer);
  }, [current, pace, reduced, step]);
  const stageIndex = reduced
    ? baseStages.length
    : Math.min(Math.floor(step / 2), baseStages.length);
  const stages = [
    ...baseStages,
    (current ?? []).some((item) => item.result_type !== "REVIEW_FINDING")
      ? "System status"
      : "Analyst review",
  ];
  const traceComplete = reduced && events.length > 0;
  const branches = current ?? [];
  return (
    <section className="panel visual-trace" aria-label="Processing trace">
      <div className="panel-head compact">
        <div>
          <h2>Processing trace</h2>
          <p>
            Visual trace only — display pacing does not represent processing
            latency.
          </p>
        </div>
        {!reduced && queuedCount > 0 && (
          <span className="count-badge">{queuedCount} queued</span>
        )}
      </div>
      <div className="trace-stages" aria-live="polite">
        {stages.map((title, index) => (
          <div
            className={`trace-stage${current && index <= stageIndex ? " is-active" : ""}`}
            key={title}
          >
            <span className="trace-dot" aria-hidden="true" />
            {title}
            {index < stages.length - 1 && (
              <span
                className={`trace-connector${current && index < stageIndex ? " is-active" : ""}`}
                aria-hidden="true"
              />
            )}
          </div>
        ))}
      </div>
      {branches.length > 0 && (
        <div
          className="trace-outcomes"
          aria-label="Results from linked source observations"
        >
          {branches.map((result) => (
            <span key={result.result_id}>
              {familyLabel(result.family.toLowerCase())} →{" "}
              {mechanismLabel(result.mechanism_id || result.lane_id)} → Evidence
            </span>
          ))}
        </div>
      )}
      {!current && (
        <p className="trace-idle">
          {traceComplete
            ? "Reduced motion is enabled. The completed path is shown immediately."
            : events.length
              ? "Trace complete. New results appear here as they arrive."
              : "Waiting for persisted results."}
        </p>
      )}
    </section>
  );
}
