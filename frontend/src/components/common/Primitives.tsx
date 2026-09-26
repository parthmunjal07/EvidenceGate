import type { ReactNode } from "react";
import type { QualitySnapshot, VisibilitySnapshot } from "../../api/types";
import { claimSemantics, pretty, readable } from "../../utils/formatting";

export function PageHeading({
  titleId,
  title,
  deck,
  meta,
}: {
  titleId?: string;
  title: string;
  deck: string;
  meta?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <h1 id={titleId}>{title}</h1>
        <p className="page-deck">{deck}</p>
      </div>
      {meta && <div className="heading-meta">{meta}</div>}
    </div>
  );
}
export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="empty-state">{children}</div>;
}
export function Notice({
  children,
  kind = "notice-bar",
}: {
  children: ReactNode;
  kind?: string;
}) {
  return (
    <div className={kind} role="status">
      {children}
    </div>
  );
}
export function InspectorSection({
  title,
  children,
  secondary = false,
}: {
  titleId?: string;
  title: string;
  children: ReactNode;
  secondary?: boolean;
}) {
  return (
    <section className="inspect-section">
      {secondary ? (
        <details>
          <summary className="inspect-section-head">
            <h3>{title}</h3>
          </summary>
          {children}
        </details>
      ) : (
        <>
          <div className="inspect-section-head">
            <h3>{title}</h3>
          </div>
          {children}
        </>
      )}
    </section>
  );
}
export function CodeBlock({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="code-field">
      <span className="field-label">{label}</span>
      <pre>{typeof value === "string" ? value : pretty(value)}</pre>
    </div>
  );
}
export function ClaimCeiling({ text }: { text: string }) {
  const claim = claimSemantics(text);
  return <div className="claim-semantics">
    <h4>What this evidence supports</h4>
    {claim.supports.length ? <ul>{claim.supports.map((item) => <li key={item}>{item}</li>)}</ul> : <p>Evidence was observed; no additional conclusion is drawn.</p>}
    <h4>What this evidence does not establish</h4>
    {claim.limitations.length ? <ul>{claim.limitations.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No additional limitation was reported.</p>}
    {claim.hasUnknown && <p>Additional evidence limits are recorded in the evidence details.</p>}
  </div>;
}
export function QualitySnapshotView({ value }: { value: QualitySnapshot }) {
  const labels: Record<string, string> = {
    packet_loss: "Packet loss",
    sampling: "Sampling",
    parser: "Parser status",
    capture_gap: "Capture gaps",
  };
  const stateLabel = (state: string) => ({ CLEAR: "Clear", DEGRADED: "Degraded", UNKNOWN: "Not reported" }[state] ?? "Not reported");
  if (Object.values(value).every((state) => state === "UNKNOWN")) return <div className="quality-summary">Capture quality: Not reported <details><summary>View quality details</summary><Snapshot rows={Object.entries(value).map(([key, state]) => [labels[key] ?? readable(key), stateLabel(state)])} /></details></div>;
  return (
    <Snapshot
      rows={Object.entries(value).map(([key, state]) => [
        labels[key] ?? readable(key),
        stateLabel(state),
      ])}
    />
  );
}
export function VisibilitySnapshotView({
  value,
}: {
  value: VisibilitySnapshot;
}) {
  const rows = (
    [
      ["available", "Available"],
      ["unavailable", "Unavailable"],
      ["degraded", "Degraded"],
    ] as const
  ).flatMap(([key, label]) => value[key].length ? [[label, value[key].map(readable).join(" · ")]] : []);
  return (
    <Snapshot
      rows={rows.length ? rows : [["Visibility", "No explicit visibility classes reported"]]}
    />
  );
}
function Snapshot({ rows }: { rows: string[][] }) {
  return (
    <div className="snapshot-list">
      {rows.map(([label, value]) => (
        <div className="snapshot-row" key={label}>
          <span className="snapshot-state">{label}</span>
          <span className="snapshot-values">{value}</span>
        </div>
      ))}
    </div>
  );
}
export function KeyValueList({ rows }: { rows: Array<[string, ReactNode]> }) {
  return (
    <dl className="inspect-list">
      {rows.map(([label, value]) => (
        <div className="inspect-pair" key={label}>
          <dt>{label}</dt>
          <dd>{value || "—"}</dd>
        </div>
      ))}
    </dl>
  );
}
