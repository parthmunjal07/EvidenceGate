import { useEffect, useRef, useState } from "react";
import type { ResultDto } from "../../api/types";
import { useReducedMotion } from "../../hooks/useReducedMotion";
import { familyLabel } from "../../utils/formatting";

const stages = ["Observed traffic", "Visibility", "Analytics", "Evidence", "Review / status"];
const demoSteps = [650, 300, 700, 300, 800, 300, 700, 300, 700];
const normalSteps = [260, 120, 280, 120, 320, 120, 280, 120, 280];
export const visualTraceTiming = { demoSteps: [...demoSteps], normalSteps: [...normalSteps], maxQueuedTraces: 3 };
const traceKey = (items: ResultDto[]) => items.map((item) => `${item.lane_id}:${item.result_type}`).sort().join("|");

export function VisualTrace({ events, pace }: { events: ResultDto[]; pace: "demo" | "normal" }) {
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
      if (seen.current.size > 64) {
        const oldest = seen.current.values().next().value;
        if (oldest) seen.current.delete(oldest);
      }
      return true;
    });
    if (!fresh.length) return;
    if (reduced) {
      active.current = null;
      queue.current = [];
      return;
    }
    const groups: ResultDto[][] = [];
    for (const result of fresh) {
      const observations = new Set(result.source_observation_ids);
      const group = observations.size ? groups.find((items) =>
        items[0]?.source_observation_ids.some((id) => observations.has(id))) : undefined;
      if (group) group.push(result);
      else groups.push([result]);
    }
    for (const group of groups) {
      const key = traceKey(group);
      if (active.current && traceKey(active.current) === key) continue;
      const existing = queue.current.find((items) => traceKey(items) === key);
      if (!existing) queue.current.push(group);
    }
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

  const stageIndex = Math.min(Math.floor(step / 2), stages.length - 1);
  const displayCurrent = reduced ? null : current;
  const families = [...new Set((current ?? []).map((item) => familyLabel(item.family.toLowerCase())))];
  const traceComplete = reduced && events.length > 0;
  return <section className="panel visual-trace" aria-label="Replay visual trace">
    <div className="panel-head compact"><div><h2>Visual trace</h2><p>Display pacing does not represent processing latency.</p></div>
      {!reduced && queuedCount > 0 && <span className="count-badge">{queuedCount} queued</span>}
    </div>
    <div className="trace-stages" aria-live="polite">
      {stages.map((title, index) => <div className={`trace-stage${displayCurrent && index <= stageIndex ? " is-active" : ""}`} key={title}>
        <span className="trace-dot" aria-hidden="true" />{title}
        {index < stages.length - 1 && <span className={`trace-connector${displayCurrent && index < stageIndex ? " is-active" : ""}`} aria-hidden="true" />}
      </div>)}
    </div>
    {displayCurrent && <div className="trace-outcomes" aria-label="Independent analytic outputs">
      {families.map((family) => <span key={family}>{family} · independent evidence</span>)}
    </div>}
    {!displayCurrent && <p className="trace-idle">{traceComplete ? "Reduced motion is enabled. Results are shown without animation." : events.length ? "Trace complete. New results appear here as they arrive." : "Waiting for persisted results."}</p>}
  </section>;
}
