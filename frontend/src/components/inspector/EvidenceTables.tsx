import type { KeyboardEvent } from "react";
import type { ResultDto, SihAlertProjection } from "../../api/types";
import {
  contextSummary,
  formatTimestamp,
  friendlyCategory,
  humanEvidenceRows,
  mechanismLabel,
  readable,
  summarizeAnalystContext,
  whySurfaced,
} from "../../utils/formatting";
import { useTimeZone } from "../../state/TimeZoneContext";

export function AlertTable({ alerts, selectedId, onSelect }: { alerts: SihAlertProjection[]; selectedId: string | null; onSelect: (item: SihAlertProjection) => void }) {
  const { zone } = useTimeZone();
  return <div className="table-wrap"><table className="data-table analyst-table"><thead><tr>{[`Observed time · ${zone === "utc" ? "UTC" : "Local"}`, "Family", "Finding", "Context", "Summary", "Evidence state"].map((name) => <th key={name}>{name}</th>)}</tr></thead><tbody>
    {alerts.map((alert) => {
      const state = Object.values(alert.quality).some((value) => value === "DEGRADED") ? "Quality degraded" : alert.visibility.unavailable.length || alert.visibility.degraded.length ? "Visibility limited" : "Available";
      const family = friendlyCategory(alert.threat_class);
      const finding = mechanismLabel(alert.mechanism_id);
      const context = summarizeAnalystContext(alert.threat_class, alert.mechanism_id, alert.entity_or_flow_reference, alert.supporting_evidence.structured);
      return <tr key={alert.alert_id} className={`selectable-row${selectedId === alert.alert_id ? " selected" : ""}`} tabIndex={0} onClick={() => onSelect(alert)} onKeyDown={(event) => selectOnKeyboard(event, () => onSelect(alert))}>
        <td><time>{formatTimestamp(alert.timestamp, zone)}</time></td><td>{family}</td><td>{finding}</td><td title={context}><span className="reference-summary">{context}</span></td><td><span className="why-surfaced-summary">{whySurfaced(alert.mechanism_id, alert.supporting_evidence.structured)}</span></td><td><span className="review-item-status">Review</span><small className="result-evidence-summary">{state}</small></td>
      </tr>;
    })}
  </tbody></table></div>;
}

export function ResultTable({ results, selectedId, onSelect }: { results: ResultDto[]; selectedId: string | null; onSelect: (item: ResultDto) => void }) {
  const { zone } = useTimeZone();
  return <div className="table-wrap"><table className="data-table evidence-table"><thead><tr>{[`Result time · ${zone === "utc" ? "UTC" : "Local"}`, "Family", "Finding", "Context", "Evidence state", "Summary"].map((name) => <th key={name}>{name}</th>)}</tr></thead><tbody>
    {results.map((result) => {
      const finding = mechanismLabel(result.mechanism_id || result.lane_id);
      const evidence = humanEvidenceRows(result.evidence)
        .map(([label, value]) => `${label}: ${value}`)
        .slice(0, 2)
        .join(" · ");
      const context = contextSummary(result);
      return <tr key={result.result_id} className={`selectable-row${selectedId === result.result_id ? " selected" : ""}`} tabIndex={0} onClick={() => onSelect(result)} onKeyDown={(event) => selectOnKeyboard(event, () => onSelect(result))}>
        <td><time>{formatTimestamp(result.created_time, zone)}</time></td><td>{friendlyCategory(result.family)}</td><td>{finding}</td><td title={context}><span className="reference-summary">{context}</span></td><td><span className="review-item-status">{readable(result.result_type)}</span></td><td><span className="why-surfaced-summary">{evidence || "Structured evidence is available."}</span></td>
      </tr>;
    })}
  </tbody></table></div>;
}

function selectOnKeyboard(event: KeyboardEvent, select: () => void) { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); select(); } }
