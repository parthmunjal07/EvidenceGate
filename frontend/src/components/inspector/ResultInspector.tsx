import type {
  ObservationPresentationDto,
  QualitySnapshot,
  ResultDto,
  VisibilitySnapshot,
} from "../../api/types";
import { dgaScoreInterpretation } from "../../utils/copy";
import {
  formatEvidenceRange,
  formatTimestamp,
  friendlyCategory,
  humanEvidenceRows,
  mechanismLabel,
  resultEvidenceStateLabel,
} from "../../utils/formatting";
import {
  formatEndpointPair,
  formatTcpBehavior,
  presentService,
  transportLabel,
} from "../../utils/networkContext";
import {
  QualitySnapshotView,
  VisibilitySnapshotView,
} from "../common/Primitives";
import { Header, Inspector } from "./InspectorShell";
import { useTimeZone } from "../../state/TimeZoneContext";
import { projectResultExplanation } from "../../utils/resultExplanation";
import { reconPresentation } from "../../utils/reconPresentation";

type Props = {
  result: ResultDto | null;
  onClose: () => void;
  availableSourceCount?: number;
  sourceObservations?: ObservationPresentationDto[];
  onOpenSource?: (index: number) => void;
  onOpenFamily?: () => void;
  onOpenInvestigation?: () => void;
  onBack?: () => void;
};

export function ResultInspector({
  result,
  onClose,
  availableSourceCount = 0,
  sourceObservations = [],
  onOpenSource,
  onOpenFamily,
  onOpenInvestigation,
  onBack,
}: Props) {
  const { zone } = useTimeZone();
  if (!result) return null;
  const evidenceRows = humanEvidenceRows(result.evidence)
    .filter(([label]) => label !== "Additional evidence")
    .map(([label, value]) =>
      label.toLowerCase() === "protocol"
        ? (["Transport", transportLabel(value)] as [string, string])
        : ([label, value] as [string, string]),
    );
  const finding = mechanismLabel(result.mechanism_id || result.lane_id);
  const isDga = result.lane_id === "dga.m1";
  const isSourceDiversity = result.lane_id === "ddos.source_diversity";
  const c2 = c2Context(result);
  const sourceLowerBound =
    result.evidence.apparent_source_cardinality_lower_bound ??
    result.evidence.unique_sources;
  const explanation = projectResultExplanation(
    result,
    [],
    sourceObservations[0] ?? null,
  );
  const recon = reconPresentation(result, sourceObservations);
  const alternatives = stringArray(result.evidence.hard_negative_alternatives);
  const interval = result.evidence_interval;
  const timeWindow = interval
    ? formatEvidenceRange(interval[0], interval[1], zone)
    : null;
  return (
    <Inspector
      key={result.result_id}
      variant="modal"
      label="Evidence record"
      selected
      onClose={onClose}
      placeholder="Select an evidence record"
      description="Review the facts recorded by one analytic."
    >
      <div className="result-detail">
        <Header
          kicker={friendlyCategory(result.family)}
          title={finding}
          subtitle={
            recon?.source ??
            (sourceObservations[0]
              ? (formatEndpointPair(sourceObservations[0].facts) ??
                "Observed network activity")
              : "Observed network evidence")
          }
          onClose={onClose}
          {...(onBack ? { onBack } : {})}
        />
        <div className="result-type-line">
          <span className="object-level-label">
            Observed {timeWindow ?? formatTimestamp(result.created_time, zone)}
          </span>
          <span className="status-chip neutral">
            {resultEvidenceStateLabel(result.result_type)}
          </span>
        </div>

        <section className="result-section result-happened">
          <h3>What happened?</h3>
          <p>
            {sourceObservations.length > 0
              ? `${sourceObservations.length} canonical source observation${sourceObservations.length === 1 ? "" : "s"} contributed to this ${finding.toLowerCase()} measurement.`
              : `${finding} evidence was recorded for the observed context.`}
          </p>
        </section>

        <section
          className="result-section result-explanation-grid"
          aria-label="Analytic explanation"
        >
          {explanation.eligibilityReasons.length > 0 && (
            <article>
              <h3>Why this analytic ran</h3>
              <p>{explanation.eligibilityReasons.join(" ")}</p>
            </article>
          )}
          <article>
            <h3>Why it was ready</h3>
            <p>{explanation.readinessReason}</p>
          </article>
          <article>
            <h3>Why this Result was produced</h3>
            <p>{explanation.resultReason}</p>
          </article>
        </section>

        <section className="result-section">
          <h3>Observed network behaviour</h3>
          {recon && (
            <>
              {recon.measurements.length > 0 && (
                <dl className="result-facts recon-measurement-grid">
                  {recon.measurements.map(([label, value]) => (
                    <div key={label}>
                      <dt>{label}</dt>
                      <dd>{value}</dd>
                    </div>
                  ))}
                </dl>
              )}
              {recon.targets.length > 0 ? (
                <div className="recon-targets">
                  <h4>Contacted targets from contributing observations</h4>
                  <ul>
                    {recon.targets.map((target) => (
                      <li
                        key={`${target.target}:${target.port}:${target.transport}:${target.service}`}
                      >
                        <strong>
                          {target.target}:{target.port}
                        </strong>
                        <span>
                          {target.transport} · {target.service}
                        </span>
                        <small>{target.basis}</small>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : (
                recon.detailsUnavailable && (
                  <p className="result-context-note">
                    Detailed contributing observations are no longer retained in
                    the active session. The aggregate measurements above remain
                    available.
                  </p>
                )
              )}
            </>
          )}
          {c2 && (
            <dl className="result-facts">
              {c2.map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          )}
          {evidenceRows.length > 0 && (
            <dl className="result-facts">
              {evidenceRows.map(([label, value]) => (
                <div key={label}>
                  <dt>
                    {isDga && label === "Domain"
                      ? "Queried domain"
                      : isSourceDiversity &&
                          label === "Minimum apparent source count"
                        ? "Current observed lower bound"
                        : label}
                  </dt>
                  <dd>
                    {isSourceDiversity &&
                    label === "Minimum apparent source count"
                      ? `${value} apparent source${value === "1" ? "" : "s"}`
                      : value}
                  </dd>
                </div>
              ))}
            </dl>
          )}
          {isSourceDiversity &&
            typeof sourceLowerBound === "number" &&
            sourceLowerBound === 1 && (
              <p className="result-context-note">
                Incremental measurement: this is the current lower bound in the
                observed window, not a statement about sources outside the
                captured evidence.
              </p>
            )}
          {sourceObservations.length > 0 && (
            <div className="result-network-observations">
              <h4>Contributing source observations</h4>
              <ul>
                {sourceObservations.slice(0, 6).map((observation) => {
                  const tcpBehavior = formatTcpBehavior(observation.facts);
                  return (
                    <li key={observation.observation_id}>
                      <strong>{observationLabel(observation)}</strong>
                      <span>
                        {transportLabel(
                          observation.facts.protocol_number ??
                            observation.facts.transport,
                        )}{" "}
                        · {serviceFor(observation)}
                      </span>
                      <small>
                        {formatTimestamp(observation.event_time, zone)} ·{" "}
                        {observation.wire_direction.toLowerCase()} direction
                        {tcpBehavior ? ` · ${tcpBehavior}` : ""}
                      </small>
                    </li>
                  );
                })}
              </ul>
              {sourceObservations.length > 6 && (
                <p>
                  {sourceObservations.length - 6} additional source observations
                  are available through review.
                </p>
              )}
            </div>
          )}
        </section>

        {isDga && <p className="semantic-note">{dgaScoreInterpretation}</p>}

        <section className="result-section result-interpretation">
          <article>
            <h3>What this supports</h3>
            <ul>
              {explanation.supports.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </article>
          <article>
            <h3>What else could explain it?</h3>
            {alternatives.length > 0 ? (
              <ul>
                {alternatives.map((item) => (
                  <li key={item}>{humanizeAlternative(item)}</li>
                ))}
              </ul>
            ) : (
              <p>
                No mechanism-specific alternative catalogue is attached to this
                Result.
              </p>
            )}
          </article>
        </section>

        <section className="result-section result-limitations">
          <h3>What is missing?</h3>
          {explanation.missingEvidence.length > 0 ? (
            <ul>
              {explanation.missingEvidence.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : (
            <p>No additional mechanism prerequisite was reported as missing.</p>
          )}
        </section>

        <section className="result-section result-limitations">
          <h3>What this does not establish</h3>
          {explanation.limitations.length > 0 ? (
            <ul>
              {explanation.limitations.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : (
            <p>No additional claim is drawn beyond the attached evidence.</p>
          )}
        </section>

        <section className="result-section result-next-actions">
          <h3>What to review next</h3>
          {availableSourceCount > 0 && onOpenSource ? (
            <details>
              <summary>
                Review {availableSourceCount} contributing source observation
                {availableSourceCount === 1 ? "" : "s"}
              </summary>
              <ul>
                {sourceObservations.map((observation, index) => (
                  <li key={observation.observation_id}>
                    <button
                      type="button"
                      className="text-button"
                      onClick={() => onOpenSource(index)}
                    >
                      Open observation {index + 1} ·{" "}
                      {formatTimestamp(observation.event_time, zone)} →
                    </button>
                  </li>
                ))}
              </ul>
            </details>
          ) : (
            <p>
              {result.source_observation_ids.length
                ? "Detailed source observations are not retained in the active session."
                : "No source observation is linked to this Result."}
            </p>
          )}
          <div className="result-next-buttons">
            {onOpenFamily && (
              <button
                type="button"
                className="secondary-button"
                onClick={onOpenFamily}
              >
                Open{" "}
                {friendlyCategory(result.family).replace(/ evidence$/i, "")}{" "}
                family evidence →
              </button>
            )}
            {onOpenInvestigation && (
              <button
                type="button"
                className="secondary-button"
                onClick={onOpenInvestigation}
              >
                Open related investigations →
              </button>
            )}
          </div>
        </section>

        <details className="result-disclosure">
          <summary>Sensor visibility and capture quality</summary>
          <div className="result-disclosure-content">
            <VisibilitySnapshotView
              value={mergeVisibility(
                result.visibility_snapshot,
                sourceObservations,
              )}
            />
            <QualitySnapshotView
              value={mergeQuality(result.quality_snapshot, sourceObservations)}
            />
          </div>
        </details>

        <div className="result-source-evidence">
          <strong>Source evidence</strong>
          <span>
            {result.source_observation_ids.length} network observation
            {result.source_observation_ids.length === 1 ? "" : "s"} contributed
          </span>
        </div>
      </div>
    </Inspector>
  );
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}
function humanizeAlternative(value: string) {
  return value
    .replaceAll("_", " ")
    .replace(/^./, (first) => first.toUpperCase());
}
function serviceFor(observation: ObservationPresentationDto) {
  const role = observation.identity.role_assignments.find(
    (item) => item.role === "service_id",
  );
  const service = presentService(role, observation.facts.destination_port);
  return `${service.label} · ${service.basis}`;
}
function mergeVisibility(
  result: VisibilitySnapshot,
  observations: ObservationPresentationDto[],
): VisibilitySnapshot {
  const values: VisibilitySnapshot = {
    available: [...result.available],
    unavailable: [...result.unavailable],
    degraded: [...result.degraded],
  };
  for (const observation of observations)
    for (const key of ["available", "unavailable", "degraded"] as const)
      values[key].push(...observation.visibility[key]);
  return {
    available: [...new Set(values.available)],
    unavailable: [...new Set(values.unavailable)],
    degraded: [...new Set(values.degraded)],
  };
}
function mergeQuality(
  result: QualitySnapshot,
  observations: ObservationPresentationDto[],
): QualitySnapshot {
  const fields: Array<keyof QualitySnapshot> = [
    "packet_loss",
    "sampling",
    "parser",
    "capture_gap",
  ];
  return Object.fromEntries(
    fields.map((field) => {
      const states = [
        result[field],
        ...observations.map((observation) => observation.quality[field]),
      ].map((state) => state.toUpperCase());
      const value = states.includes("DEGRADED")
        ? "DEGRADED"
        : states.includes("CLEAR")
          ? "CLEAR"
          : "UNKNOWN";
      return [field, value];
    }),
  ) as QualitySnapshot;
}
function observationLabel(observation: ObservationPresentationDto) {
  const endpoints = formatEndpointPair(observation.facts);
  if (endpoints) return endpoints;
  const domain =
    observation.facts.qname_rendered ?? observation.facts.qname_canonical;
  return typeof domain === "string" ? domain : "Network facts recorded";
}

function c2Context(result: ResultDto): Array<[string, string]> | null {
  if (!result.lane_id.startsWith("c2.")) return null;
  const entity = asRecord(result.evidence.entity);
  const measurements = asRecord(result.evidence.measurements);
  const client = textValue(entity?.client_ref);
  const peer = textValue(entity?.peer_ref);
  const serviceRef = textValue(entity?.service_ref);
  const numericPort =
    serviceRef && /^\d+$/.test(serviceRef) ? serviceRef : null;
  const protocol = transportLabel(entity?.protocol);
  const eventCount =
    numberValue(measurements?.event_count) ??
    numberValue(result.evidence.observed_event_count);
  const historySpan = numberValue(measurements?.history_span_seconds);
  const rows: Array<[string, string]> = [];
  if (client) rows.push(["Client", client]);
  if (peer)
    rows.push(["Peer", `${peer}${numericPort ? `:${numericPort}` : ""}`]);
  if (numericPort) rows.push(["Peer port", numericPort]);
  if (entity?.protocol !== undefined && protocol !== "Not reported")
    rows.push(["Transport", protocol]);
  if (eventCount !== null)
    rows.push(["Communication events", String(eventCount)]);
  if (historySpan !== null)
    rows.push(["Observed history span", `${historySpan} s`]);
  return rows.length ? rows : null;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function textValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
