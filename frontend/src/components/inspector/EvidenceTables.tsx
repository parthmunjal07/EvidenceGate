import type { KeyboardEvent } from "react";
import type { ResultDto, SihAlertProjection } from "../../api/types";
import { formatShortTime, friendlyCategory, formatEvidenceValue, mechanismLabel, readable, summarizeReference, whySurfaced } from "../../utils/formatting";

export function AlertTable({ alerts, selectedId, onSelect }: { alerts: SihAlertProjection[]; selectedId: string | null; onSelect: (item: SihAlertProjection) => void }) {
  return <div className="table-wrap"><table className="data-table analyst-table"><thead><tr>{["Time", "Category", "Entity / peer", "Why surfaced", "Context"].map((name) => <th key={name}>{name}</th>)}</tr></thead><tbody>
    {alerts.map((alert) => {
      const context = Object.values(alert.quality).some((value) => value === "DEGRADED") ? "Quality degraded" : alert.visibility.unavailable.length ? "Visibility limited" : alert.visibility.degraded.length ? "Visibility limited" : "—";
      return <tr key={alert.alert_id} className={`selectable-row${selectedId === alert.alert_id ? " selected" : ""}`} tabIndex={0} onClick={() => onSelect(alert)} onKeyDown={(event) => selectOnKeyboard(event, () => onSelect(alert))}>
        <td><time>{formatShortTime(alert.timestamp)}</time></td><td>{friendlyCategory(alert.threat_class)}</td><td title={alert.entity_or_flow_reference}><span className="reference-summary">{summarizeReference(alert.entity_or_flow_reference, alert.mechanism_id)}</span></td><td><span className="why-surfaced-summary">{whySurfaced(alert.mechanism_id, alert.supporting_evidence.structured)}</span></td><td>{context}</td>
      </tr>;
    })}
  </tbody></table></div>;
}
export function ResultTable({ results, selectedId, onSelect }: { results: ResultDto[]; selectedId: string | null; onSelect: (item: ResultDto) => void }) {
  return <div className="table-wrap"><table className="data-table evidence-table"><thead><tr>{["Time", "Category", "Finding", "Entity", "Result"].map((name) => <th key={name}>{name}</th>)}</tr></thead><tbody>
    {results.map((result) => {
      const finding = mechanismLabel(result.mechanism_id || result.lane_id);
      const evidence = Object.entries(result.evidence).filter(([key]) => !/claim[_ ]?(ceiling|limit)/i.test(key)).map(([key, value]) => formatEvidenceValue(key, value)).filter(Boolean).slice(0, 2).join(" · ");
      return <tr key={result.result_id} className={`selectable-row${selectedId === result.result_id ? " selected" : ""}`} tabIndex={0} onClick={() => onSelect(result)} onKeyDown={(event) => selectOnKeyboard(event, () => onSelect(result))}>
        <td><time>{formatShortTime(result.created_time)}</time></td><td>{friendlyCategory(result.family)}</td><td>{finding}</td><td title={result.entity_reference}><span className="reference-summary">{summarizeReference(result.entity_reference, result.mechanism_id)}</span></td><td>{readable(result.result_type)}{evidence ? <small className="result-evidence-summary">{evidence}</small> : null}</td>
      </tr>;
    })}
  </tbody></table></div>;
}
function selectOnKeyboard(event: KeyboardEvent, select: () => void) { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); select(); } }
