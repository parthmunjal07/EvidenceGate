import type { ResultDto } from "../../api/types";
import { dgaScoreInterpretation } from "../../utils/copy";
import { contextSummary, formatTimestamp, friendlyCategory, humanEvidenceRows, mechanismLabel, prerequisiteLabel, readable, whySurfaced } from "../../utils/formatting";
import { ClaimCeiling, QualitySnapshotView, VisibilitySnapshotView } from "../common/Primitives";
import { Header, Inspector } from "./InspectorShell";
import { useTimeZone } from "../../state/TimeZoneContext";
import { projectResultExplanation } from "../../utils/resultExplanation";

export function ResultInspector({ result, onClose }: { result: ResultDto | null; onClose: () => void }) {
  const { zone } = useTimeZone();
  if (!result) return null;
  const evidenceRows = humanEvidenceRows(result.evidence).filter(([label]) => label !== "Additional evidence");
  const finding = mechanismLabel(result.mechanism_id || result.lane_id);
  const isDga = result.lane_id === "dga.m1";
  const explanation = projectResultExplanation(result);
  return <Inspector key={result.result_id} variant="modal" label="Evidence record" selected onClose={onClose} placeholder="Select an evidence record" description="Review the facts recorded by one analytic.">
    <div className="result-detail">
      <Header kicker={friendlyCategory(result.family)} title={finding} subtitle={contextSummary(result)} onClose={onClose} />
      <div className="result-type-line"><span className="object-level-label">Result time: {formatTimestamp(result.created_time, zone)}</span><span className="status-chip neutral">{readable(result.result_type)}</span></div>

      <section className="result-section result-why">
        <h3>Why this Result was produced</h3>
        <p>{whySurfaced(result.mechanism_id || result.lane_id, result.evidence)}</p>
      </section>

      <section className="result-section">
        <h3>What was observed</h3>
        <dl className="result-facts">
          <div><dt>{isDga ? "Domain" : "Context"}</dt><dd>{contextSummary(result)}</dd></div>
          {evidenceRows.filter(([label]) => label !== "Domain").map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
          {evidenceRows.length === 0 && explanation.observedFacts.map((fact) => <div key={fact}><dt>Observed fact</dt><dd>{fact}</dd></div>)}
        </dl>
      </section>

      {isDga && <p className="semantic-note">{dgaScoreInterpretation}</p>}

      <section className="result-section">
        <h3>What this supports</h3>
        <ul>{explanation.supports.map((item) => <li key={item}>{item}</li>)}</ul>
        <h3>What it does not establish</h3>
        {explanation.limitations.length ? <ul>{explanation.limitations.map((item) => <li key={item}>{item}</li>)}</ul> : <ClaimCeiling text={result.claim_ceiling} />}
      </section>

      {result.missing_prerequisites.length > 0 && <section className="result-section result-limitations">
        <h3>Evidence limits</h3>
        <ul>{result.missing_prerequisites.map((item) => <li key={item}>{prerequisiteLabel(item)}</li>)}</ul>
      </section>}

      <details className="result-disclosure">
        <summary>Visibility and quality</summary>
        <div className="result-disclosure-content"><VisibilitySnapshotView value={result.visibility_snapshot} /><QualitySnapshotView value={result.quality_snapshot} /></div>
      </details>

      <details className="result-disclosure technical-details">
        <summary>Audit details</summary>
        <dl className="technical-metadata">
          <Meta label="Result ID" value={result.result_id} />
          <Meta label="Mechanism ID" value={result.mechanism_id} />
          <Meta label="Lane ID" value={result.lane_id} />
          <Meta label="Plugin" value={`${result.plugin_id} · ${result.plugin_version}`} />
          <Meta label="Analytic version" value={result.analytic_version} />
          <Meta label="Governance version" value={result.governance_version} />
          <Meta label="Model references" value={result.model_refs.join(" · ")} />
          <Meta label="Configuration hash" value={result.config_hash} />
          <Meta label="Parser references" value={result.parser_refs.join(" · ")} />
          <Meta label="Representation" value={representationLabel(result.evidence)} />
        </dl>
        <h3>Source lineage</h3>
        <span className="field-label">{result.source_observation_ids.length} {result.source_observation_ids.length === 1 ? "observation" : "observations"}</span>
        <ul className="technical-id-list">{result.source_observation_ids.map((id) => <li key={id}>{id}</li>)}</ul>
      </details>
    </div>
  </Inspector>;
}

function Meta({ label, value }: { label: string; value: string | null | undefined }) {
  return value ? <div><dt>{label}</dt><dd>{value}</dd></div> : null;
}

function representationLabel(evidence: Record<string, unknown>) {
  const value = evidence.representation;
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  const id = (value as Record<string, unknown>).m1_representation_version;
  return typeof id === "string" ? id : null;
}
