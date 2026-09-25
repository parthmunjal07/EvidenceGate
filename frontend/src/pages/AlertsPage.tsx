import { useMemo, useState } from "react";
import type { SihAlertProjection } from "../api/types";
import { AlertInspector, AlertTable } from "../components/inspector/Inspectors";
import { EmptyState, PageHeading } from "../components/common/Primitives";
import { useEvidence } from "../state/EvidenceContext";
import { filterAlerts } from "../utils/filters";
import { alertReviewDisclaimer } from "../utils/copy";
import { friendlyCategory } from "../utils/formatting";

export function AlertsPage({ initialAlert, clearInitial, openResult }: { initialAlert: SihAlertProjection | null; clearInitial: () => void; openResult: (id: string) => void }) {
  const { state } = useEvidence();
  const [search, setSearch] = useState("");
  const [threatClass, setThreatClass] = useState("");
  const [basis, setBasis] = useState("");
  const [quality, setQuality] = useState("");
  const [visibility, setVisibility] = useState("");
  const [selected, setSelected] = useState<SihAlertProjection | null>(initialAlert);
  const classes = [...new Set(state.alerts.map((item) => item.threat_class))].sort();
  const items = useMemo(() => filterAlerts(state.alerts, { search, threatClass, basis, quality, visibility }), [state.alerts, search, threatClass, basis, quality, visibility]);
  return <section className="page active-page" aria-labelledby="alerts-title">
    <PageHeading titleId="alerts-title" title="Analyst queue" deck="Evidence items brought forward for analyst review." meta={<span>{alertReviewDisclaimer}</span>} />
    <div className="filter-bar analyst-filter-bar">
      <label className="search-control"><span aria-hidden="true">⌕</span><input type="search" placeholder="Search IP, domain, flow or category" aria-label="Search analyst queue" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
      <label>Category<select value={threatClass} onChange={(event) => setThreatClass(event.target.value)}><option value="">All categories</option>{classes.map((value) => <option key={value} value={value}>{friendlyCategory(value)}</option>)}</select></label>
      <details className="more-filters"><summary>More filters</summary><div>
        <label>Evidence basis<select value={basis} onChange={(event) => setBasis(event.target.value)}><option value="">All evidence bases</option><option value="MODEL_SCORE">Lexical model score</option><option value="STATISTICAL_SUPPORT">Statistical support</option><option value="OBSERVED_EVIDENCE">Observed evidence</option></select></label>
        <label>Quality<select value={quality} onChange={(event) => setQuality(event.target.value)}><option value="">All quality states</option><option>Degraded</option><option>Clear</option><option>Unknown</option></select></label>
        <label>Visibility<select value={visibility} onChange={(event) => setVisibility(event.target.value)}><option value="">All visibility states</option><option value="available">Evidence available</option><option value="unavailable">Evidence unavailable</option><option value="degraded">Evidence degraded</option></select></label>
      </div></details>
      <span className="result-total" role="status" aria-live="polite">{items.length} {items.length === 1 ? "item" : "items"}</span>
    </div>
    <div className="investigation-layout">
      <section className="panel table-panel">{items.length ? <AlertTable alerts={items} selectedId={selected?.alert_id ?? null} onSelect={(item) => { setSelected(item); clearInitial(); }} /> : <EmptyState>No alerts match these filters.</EmptyState>}</section>
      <AlertInspector alert={selected} onClose={() => { setSelected(null); clearInitial(); }} onResult={openResult} />
    </div>
  </section>;
}
