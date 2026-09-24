import type { ReactNode } from "react";
import type { QualitySnapshot, VisibilitySnapshot } from "../../api/types";
import { pretty } from "../../utils/formatting";

export function PageHeading({
  eyebrow,
  title,
  deck,
  meta,
}: {
  eyebrow: string;
  title: string;
  deck: string;
  meta?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
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
  return <p className="claim-text">{text}</p>;
}
export function QualitySnapshotView({ value }: { value: QualitySnapshot }) {
  return (
    <Snapshot
      rows={Object.entries(value).map(([key, state]) => [
        `${state === "CLEAR" ? "✓" : state === "DEGRADED" ? "!" : "○"} ${key.replaceAll("_", " ")}`,
        state,
      ])}
    />
  );
}
export function VisibilitySnapshotView({
  value,
}: {
  value: VisibilitySnapshot;
}) {
  return (
    <Snapshot
      rows={(
        [
          ["available", "✓ Available"],
          ["unavailable", "× Unavailable"],
          ["degraded", "! Degraded"],
        ] as const
      ).map(([key, label]) => [
        label,
        value[key].join(" · ") || "None reported",
      ])}
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
