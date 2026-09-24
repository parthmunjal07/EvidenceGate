import { useMemo, useState } from "react";
import type { SihAlertProjection } from "../api/types";
import { AlertInspector, AlertTable } from "../components/inspector/Inspectors";
import { EmptyState, PageHeading } from "../components/common/Primitives";
import { useEvidence } from "../state/EvidenceContext";
import { filterAlerts } from "../utils/filters";
import type { PageKey } from "../state/types";

export function AlertsPage({
  initialAlert,
  navigate,
  clearInitial,
  openResult,
}: {
  initialAlert: SihAlertProjection | null;
  navigate: (page: PageKey) => void;
  clearInitial: () => void;
  openResult: (id: string) => void;
}) {
  const { state } = useEvidence();
  const [search, setSearch] = useState("");
  const [threatClass, setThreatClass] = useState("");
  const [basis, setBasis] = useState("");
  const [quality, setQuality] = useState("");
  const [visibility, setVisibility] = useState("");
  const [selected, setSelected] = useState<SihAlertProjection | null>(
    initialAlert,
  );
  const classes = [
    ...new Set(state.alerts.map((item) => item.threat_class)),
  ].sort();
  const items = useMemo(
    () =>
      filterAlerts(state.alerts, {
        search,
        threatClass,
        basis,
        quality,
        visibility,
      }),
    [state.alerts, search, threatClass, basis, quality, visibility],
  );
  return (
    <section className="page active-page" aria-labelledby="alerts-title">
      <PageHeading
        eyebrow="INVESTIGATION / SIH_ALERT_POLICY_V1"
        title="Analyst Alerts"
        deck="A review queue derived from immutable results for analyst attention."
        meta={
          <>
            <span className="status-chip">
              {state.runtime?.alert_policy_version ?? "Unavailable"}
            </span>
            <span>
              Alert means analyst attention, not confirmed malicious activity.
            </span>
          </>
        }
      />
      <div className="notice-bar">
        <span className="notice-icon">i</span>
        <p>
          <strong>Presentation layer</strong> — /alerts is a versioned SIH
          projection. Open{" "}
          <button className="inline-link" onClick={() => navigate("results")}>
            Evidence Results
          </button>{" "}
          for the scientific authority.
        </p>
      </div>
      <div className="filter-bar">
        <label className="search-control">
          <span aria-hidden="true">⌕</span>
          <input
            type="search"
            placeholder="Search entity, class, mechanism"
            aria-label="Search analyst alerts"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <label>
          Class
          <select
            value={threatClass}
            onChange={(e) => setThreatClass(e.target.value)}
          >
            <option value="">All classes</option>
            {classes.map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <label>
          Confidence basis
          <select value={basis} onChange={(e) => setBasis(e.target.value)}>
            <option value="">All bases</option>
            {["MODEL_SCORE", "STATISTICAL_SUPPORT", "OBSERVED_EVIDENCE"].map(
              (value) => (
                <option key={value}>{value}</option>
              ),
            )}
          </select>
        </label>
        <label>
          Quality
          <select value={quality} onChange={(e) => setQuality(e.target.value)}>
            <option value="">All quality states</option>
            <option>Degraded</option>
            <option>Clear</option>
            <option>Unknown</option>
          </select>
        </label>
        <label>
          Visibility
          <select
            value={visibility}
            onChange={(e) => setVisibility(e.target.value)}
          >
            <option value="">All visibility states</option>
            <option value="available">Evidence available</option>
            <option value="unavailable">Evidence unavailable</option>
            <option value="degraded">Evidence degraded</option>
          </select>
        </label>
        <span className="result-total" role="status" aria-live="polite">
          {items.length} records
        </span>
      </div>
      <div className="investigation-layout">
        <section className="panel table-panel">
          {items.length ? (
            <AlertTable
              alerts={items}
              selectedId={selected?.alert_id ?? null}
              onSelect={(item) => {
                setSelected(item);
                clearInitial();
              }}
            />
          ) : (
            <EmptyState>No alerts match these filters.</EmptyState>
          )}
        </section>
        <AlertInspector
          alert={selected}
          onClose={() => {
            setSelected(null);
            clearInitial();
          }}
          onResult={openResult}
        />
      </div>
      <section className="status-separation">
        <div>
          <p className="eyebrow">SEPARATE OPERATIONAL VIEW</p>
          <h2>System &amp; Evidence Status</h2>
          <p>
            Quality, capability, and evidence lifecycle records do not enter the
            analyst alert queue.
          </p>
        </div>
        <button className="secondary-button" onClick={() => navigate("system")}>
          View status records →
        </button>
      </section>
    </section>
  );
}
