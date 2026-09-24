import type { KeyboardEvent } from "react";
import type { ResultDto, SihAlertProjection } from "../../api/types";
import {
  availableCount,
  formatQuality,
  formatShortTime,
  readable,
  shortModelRef,
  summarizeEvidence,
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
              "TIME",
              "THREAT CLASS",
              "MECHANISM",
              "ENTITY / FLOW",
              "EVIDENCE",
              "CONFIDENCE BASIS",
              "QUALITY",
              "VISIBILITY",
              "PRIORITY",
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
              <td>{formatShortTime(alert.timestamp)}</td>
              <td>{alert.threat_class}</td>
              <td>{alert.mechanism_id}</td>
              <td>{alert.entity_or_flow_reference}</td>
              <td className="evidence-cell">
                {summarizeEvidence(alert.supporting_evidence.structured)}
                {alert.confidence_basis === "MODEL_SCORE"
                  ? ` Â· ${shortModelRef(alert.model_refs)}`
                  : ""}
              </td>
              <td>{alert.confidence_basis}</td>
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
              "TIME",
              "FAMILY",
              "LANE",
              "MECHANISM",
              "RESULT TYPE",
              "ENTITY / FLOW",
              "EVIDENCE SUMMARY",
              "QUALITY",
              "VISIBILITY",
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
              <td>{formatShortTime(result.created_time)}</td>
              <td>{result.family}</td>
              <td>{result.lane_id}</td>
              <td>{result.mechanism_id || "â€”"}</td>
              <td>{readable(result.result_type)}</td>
              <td>{result.entity_reference}</td>
              <td className="evidence-cell">
                {summarizeEvidence(result.evidence)}
                {result.lane_id === "dga.m1"
                  ? ` Â· ${shortModelRef(result.model_refs)}`
                  : ""}
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
