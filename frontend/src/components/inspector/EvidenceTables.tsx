import type { KeyboardEvent } from "react";
import type { ResultDto, SihAlertProjection } from "../../api/types";
import {
  contextSummary,
  formatEvidenceDateTimeCompact,
  formatEvidenceTableClock,
  formatEvidenceTableDate,
  formatTimeZoneLabel,
  formatTimestamp,
  friendlyCategory,
  mechanismLabel,
  normalizeFamilyName,
  resultEvidenceStateLabel,
  resultEvidenceStateTone,
  resultEvidenceSummary,
  summarizeAnalystContext,
  whySurfaced,
} from "../../utils/formatting";
import { useTimeZone } from "../../state/TimeZoneContext";

export function AlertTable({
  alerts,
  selectedId,
  onSelect,
}: {
  alerts: SihAlertProjection[];
  selectedId: string | null;
  onSelect: (item: SihAlertProjection) => void;
}) {
  const { zone } = useTimeZone();
  return (
    <div className="table-wrap">
      <table className="data-table analyst-table">
        <thead>
          <tr>
            {[
              `Observed time · ${zone === "utc" ? "UTC" : "Local"}`,
              "Family",
              "Finding",
              "Context",
              "Summary",
              "Evidence state",
            ].map((name) => (
              <th key={name}>{name}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {alerts.map((alert) => {
            const state = Object.values(alert.quality).some(
              (value) => value === "DEGRADED",
            )
              ? "Quality degraded"
              : alert.visibility.unavailable.length ||
                  alert.visibility.degraded.length
                ? "Visibility limited"
                : "Available";
            const family = friendlyCategory(alert.threat_class);
            const finding = mechanismLabel(alert.mechanism_id);
            const context = summarizeAnalystContext(
              alert.threat_class,
              alert.mechanism_id,
              alert.entity_or_flow_reference,
              alert.supporting_evidence.structured,
            );
            return (
              <tr
                key={alert.alert_id}
                className={`selectable-row${selectedId === alert.alert_id ? " selected" : ""}`}
                tabIndex={0}
                onClick={() => onSelect(alert)}
                onKeyDown={(event) =>
                  selectOnKeyboard(event, () => onSelect(alert))
                }
              >
                <td>
                  <time>{formatTimestamp(alert.timestamp, zone)}</time>
                </td>
                <td>{family}</td>
                <td>{finding}</td>
                <td title={context}>
                  <span className="reference-summary">{context}</span>
                </td>
                <td>
                  <span className="why-surfaced-summary">
                    {whySurfaced(
                      alert.mechanism_id,
                      alert.supporting_evidence.structured,
                    )}
                  </span>
                </td>
                <td>
                  <span className="review-item-status">Review</span>
                  <small className="result-evidence-summary">{state}</small>
                </td>
              </tr>
            );
          })}
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
  const { zone } = useTimeZone();
  return (
    <div className="table-wrap">
      <table className="data-table evidence-table">
        <colgroup>
          <col className="col-time" />
          <col className="col-family" />
          <col className="col-finding" />
          <col className="col-context" />
          <col className="col-state" />
          <col className="col-summary" />
        </colgroup>
        <thead>
          <tr>
            {[
              `Result time · ${formatTimeZoneLabel(zone)}`,
              "Family",
              "Finding",
              "Context",
              "Evidence state",
              "Summary",
            ].map((name) => (
              <th key={name}>{name}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {results.map((result) => {
            const finding = mechanismLabel(
              result.mechanism_id || result.lane_id,
            );
            const context = contextSummary(result);
            return (
              <tr
                key={result.result_id}
                className={`selectable-row${selectedId === result.result_id ? " selected" : ""}`}
                tabIndex={0}
                onClick={() => onSelect(result)}
                onKeyDown={(event) =>
                  selectOnKeyboard(event, () => onSelect(result))
                }
              >
                <td className="evidence-time-cell">
                  <time
                    dateTime={result.created_time ?? undefined}
                    title={`Observed / Result time: ${formatEvidenceDateTimeCompact(result.created_time, zone)} ${formatTimeZoneLabel(zone)}`}
                  >
                    <span>
                      {formatEvidenceTableDate(result.created_time, zone)}
                    </span>
                    <strong>
                      {formatEvidenceTableClock(result.created_time, zone)}
                    </strong>
                  </time>
                </td>
                <td>{normalizeFamilyName(result.family)}</td>
                <td>
                  <span className="evidence-finding">{finding}</span>
                </td>
                <td title={context}>
                  <span className="reference-summary">{context}</span>
                </td>
                <td>
                  <span
                    className={`evidence-state evidence-state-${resultEvidenceStateTone(result.result_type)}`}
                  >
                    {resultEvidenceStateLabel(result.result_type)}
                  </span>
                </td>
                <td title={resultEvidenceSummary(result)}>
                  <span className="evidence-summary">
                    {resultEvidenceSummary(result)}
                  </span>
                </td>
              </tr>
            );
          })}
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
