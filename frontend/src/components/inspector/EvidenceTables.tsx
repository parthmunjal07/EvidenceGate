import type { KeyboardEvent } from "react";
import type { ResultDto, SihAlertProjection } from "../../api/types";
import {
  availableCount,
  confidenceBasisLabel,
  formatQuality,
  formatShortTime,
  readable,
  shortModelRef,
  summarizeTableEvidence,
  summarizeReference,
  threatClassLabel,
} from "../../utils/formatting";
export function AlertTable({
  alerts,
  selectedId,
  onSelect,
}: {
  alerts: SihAlertProjection[];
  selectedId: string | null;
  onSelect: (item: SihAlertProjection) => void;
}) {
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            {[
              "Time",
              "Threat class",
              "Mechanism",
              "Entity",
              "Evidence",
              "Confidence basis",
              "Quality",
              "Visibility",
              "Priority",
            ].map((name) => (
              <th key={name}>{name}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {alerts.map((alert) => (
            <tr
              key={alert.alert_id}
              className={`selectable-row${selectedId === alert.alert_id ? " selected" : ""}`}
              tabIndex={0}
              onClick={() => onSelect(alert)}
              onKeyDown={(event) =>
                selectOnKeyboard(event, () => onSelect(alert))
              }
            >
              <td><time>{formatShortTime(alert.timestamp)}</time></td>
              <td>{threatClassLabel(alert.threat_class)}</td>
              <td><code>{alert.mechanism_id}</code></td>
              <td title={alert.entity_or_flow_reference}><span className="reference-summary">{summarizeReference(alert.entity_or_flow_reference, alert.mechanism_id)}</span></td>
              <td className="evidence-cell">
                <span className="cell-summary">
                  {summarizeTableEvidence(alert.supporting_evidence.structured)}
                  {alert.confidence_basis === "MODEL_SCORE" && (
                    <code> · {shortModelRef(alert.model_refs)}</code>
                  )}
                </span>
              </td>
              <td>{confidenceBasisLabel(alert.confidence_basis)}</td>
              <td>{formatQuality(alert.quality)}</td>
              <td>{availableCount(alert.visibility)} available</td>
              <td className="priority-text">Review</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
export function ResultTable({
  results,
  selectedId,
  onSelect,
}: {
  results: ResultDto[];
  selectedId: string | null;
  onSelect: (item: ResultDto) => void;
}) {
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            {[
              "Time",
              "Family",
              "Lane",
              "Mechanism",
              "Result type",
              "Entity",
              "Evidence",
              "Quality",
              "Visibility",
            ].map((name) => (
              <th key={name}>{name}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {results.map((result) => (
            <tr
              key={result.result_id}
              className={`selectable-row${selectedId === result.result_id ? " selected" : ""}`}
              tabIndex={0}
              onClick={() => onSelect(result)}
              onKeyDown={(event) =>
                selectOnKeyboard(event, () => onSelect(result))
              }
            >
              <td><time>{formatShortTime(result.created_time)}</time></td>
              <td>{result.family}</td>
              <td><code>{result.lane_id}</code></td>
              <td><code>{result.mechanism_id || "â€”"}</code></td>
              <td>{readable(result.result_type)}</td>
              <td title={result.entity_reference}><span className="reference-summary">{summarizeReference(result.entity_reference, result.mechanism_id)}</span></td>
              <td className="evidence-cell">
                <span className="cell-summary">
                  {summarizeTableEvidence(result.evidence)}
                  {result.lane_id === "dga.m1" && (
                    <code> · {shortModelRef(result.model_refs)}</code>
                  )}
                </span>
              </td>
              <td>{formatQuality(result.quality_snapshot)}</td>
              <td>{availableCount(result.visibility_snapshot)} available</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function selectOnKeyboard(event: KeyboardEvent, select: () => void) {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    select();
  }
}
