import { useEffect, useRef, useState, type ReactNode } from "react";
import type { PageKey } from "../../state/types";
import { useEvidence } from "../../state/EvidenceContext";
import { useTimeZone } from "../../state/TimeZoneContext";
import { formatTimeZoneLabel } from "../../utils/formatting";
import {
  checkReleaseCompatibility,
  RELEASE_RECOVERY_KEY,
} from "../../utils/releaseCompatibility";
import { ModalPortal } from "../common/ModalPortal";

const links: Array<[PageKey, string]> = [
  ["overview", "Overview"],
  ["replay", "Traffic Lab"],
  ["alerts", "Analyst Queue"],
  ["investigations", "Investigations"],
  ["results", "Evidence"],
];

export function AppShell({
  page,
  onNavigate,
  children,
}: {
  page: PageKey;
  onNavigate: (page: PageKey) => void;
  children: ReactNode;
}) {
  const { state } = useEvidence();
  const { zone, setZone } = useTimeZone();
  const [healthOpen, setHealthOpen] = useState(false);
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const developerUi = import.meta.env.VITE_EVIDENCEGATE_DEV_UI === "true";
  const healthButton = useRef<HTMLButtonElement>(null);
  const diagnosticClose = useRef<HTMLButtonElement>(null);
  const runtime = state.runtime;
  const badge = state.pageError
    ? "Offline"
    : state.replay?.state === "RUNNING"
      ? "Replaying"
      : runtime
        ? "Online"
        : "Connecting";

  useEffect(() => {
    if (!healthOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setHealthOpen(false);
        healthButton.current?.focus();
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [healthOpen]);
  useEffect(() => {
    if (diagnosticsOpen) diagnosticClose.current?.focus();
  }, [diagnosticsOpen]);

  const dgaRefs = [...state.results.values()]
    .filter((result) => result.lane_id === "dga.m1")
    .flatMap((result) => result.model_refs ?? []);
  const modelSha =
    dgaRefs.find(
      (ref) => typeof ref === "string" && ref.startsWith("sha256:"),
    ) ?? "Unavailable from runtime status";
  const releaseCheck = runtime
    ? checkReleaseCompatibility(
        __EVIDENCEGATE_RELEASE_ID__,
        runtime.release_id,
        runtime.api_contract_version,
        window.sessionStorage.getItem(RELEASE_RECOVERY_KEY) === "true",
        window.location.href,
      )
    : null;
  const releaseState = releaseCheck?.state;
  const releaseReloadUrl =
    releaseCheck?.state === "reload" ? releaseCheck.url : null;
  useEffect(() => {
    if (releaseReloadUrl) {
      window.sessionStorage.setItem(RELEASE_RECOVERY_KEY, "true");
      window.location.replace(releaseReloadUrl);
    } else if (releaseState === "compatible") {
      window.sessionStorage.removeItem(RELEASE_RECOVERY_KEY);
    }
  }, [releaseReloadUrl, releaseState]);
  const refreshApplication = () => {
    const url = new URL(window.location.href);
    url.searchParams.set("eg_refresh", String(Date.now()));
    window.location.assign(url.toString());
  };
  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <a
          className="brand"
          href="#/overview"
          onClick={(event) => {
            event.preventDefault();
            onNavigate("overview");
          }}
        >
          <span className="brand-mark" aria-hidden="true">
            EG
          </span>
          <span>
            <strong>EvidenceGate</strong>
          </span>
        </a>
        <nav className="primary-nav">
          {links.map(([key, label]) => (
            <button
              type="button"
              key={key}
              data-page={key}
              onClick={() => onNavigate(key)}
              className={`nav-item${page === key ? " active" : ""}`}
              aria-current={page === key ? "page" : undefined}
            >
              <span className="nav-icon" aria-hidden="true">
                <NavIcon name={key} />
              </span>
              {label}
            </button>
          ))}
        </nav>
        <div className="sidebar-spacer" />
        <div className="sidebar-foot">
          <p>Controlled passive inputs</p>
        </div>
      </aside>
      <div className="main-column">
        <header className="topbar">
          <div className="breadcrumbs">
            <span>Security evidence</span>
          </div>
          <div className="topbar-right">
            <button
              ref={healthButton}
              type="button"
              className="runtime-pill health-trigger"
              aria-expanded={healthOpen}
              aria-haspopup="dialog"
              onClick={() => setHealthOpen((open) => !open)}
            >
              <span
                className={`runtime-dot${badge === "Offline" ? " offline" : ""}`}
              />
              <strong>{badge}</strong>
            </button>
            <label className="timezone-control">
              Time zone:{" "}
              <select
                aria-label="Evidence time display zone"
                value={zone}
                onChange={(event) =>
                  setZone(event.target.value as "local" | "utc")
                }
              >
                <option value="local">
                  Local ({formatTimeZoneLabel("local")})
                </option>
                <option value="utc">UTC</option>
              </select>
            </label>
          </div>
          {healthOpen && (
            <div
              className="health-popover"
              role="dialog"
              aria-label="System health"
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  setHealthOpen(false);
                  healthButton.current?.focus();
                }
              }}
            >
              <div className="health-popover-head">
                <h2>System health</h2>
                <button
                  aria-label="Close system health"
                  onClick={() => {
                    setHealthOpen(false);
                    healthButton.current?.focus();
                  }}
                >
                  ×
                </button>
              </div>
              <dl>
                <div>
                  <dt>Runtime</dt>
                  <dd>{badge}</dd>
                </div>
                <div>
                  <dt>Analytics</dt>
                  <dd>{runtime ? runtime.targets.length : 0} registered</dd>
                </div>
                <div>
                  <dt>Evidence store</dt>
                  <dd>
                    {runtime?.database_status === "connected"
                      ? "Available"
                      : "Checking"}
                  </dd>
                </div>
                <div>
                  <dt>Input</dt>
                  <dd>
                    {state.replay?.state === "RUNNING"
                      ? (state.replay.source_type ?? "Replay")
                      : "Controlled replay"}
                  </dd>
                </div>
              </dl>
              {developerUi && (
                <button
                  className="text-button"
                  onClick={() => {
                    setHealthOpen(false);
                    setDiagnosticsOpen(true);
                  }}
                >
                  Technical details →
                </button>
              )}
            </div>
          )}
        </header>
        <main id="main-content">
          {(state.pageError || state.streamState === "reconnecting") && (
            <div className="connection-notice" role="status">
              <strong>
                {state.pageError
                  ? "Unable to reach EvidenceGate"
                  : "Reconnecting to the service"}
              </strong>
              <span>
                Previously captured evidence remains available if already
                loaded. Check backend connectivity if this persists.
              </span>
            </div>
          )}
          {releaseCheck?.state === "warning" && (
            <div className="release-warning" role="status">
              <span>
                <strong>EvidenceGate is updating.</strong> The application files
                are temporarily on different releases.
              </span>
              <button
                type="button"
                className="text-button"
                onClick={refreshApplication}
              >
                Reload
              </button>
            </div>
          )}
          {children}
        </main>
      </div>
      {diagnosticsOpen && (
        <ModalPortal className="diagnostics-layer">
          <button
            className="drawer-backdrop"
            aria-label="Close system diagnostics"
            onClick={() => setDiagnosticsOpen(false)}
          />
          <aside
            className="diagnostics-drawer"
            role="dialog"
            aria-modal="true"
            aria-labelledby="diagnostics-title"
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                setDiagnosticsOpen(false);
                healthButton.current?.focus();
              }
            }}
          >
            <div className="inspector-head">
              <div>
                <span className="eyebrow">System diagnostics</span>
                <h2 id="diagnostics-title">Technical details</h2>
              </div>
              <button
                ref={diagnosticClose}
                className="inspector-close"
                aria-label="Close diagnostics"
                onClick={() => {
                  setDiagnosticsOpen(false);
                  healthButton.current?.focus();
                }}
              >
                ×
              </button>
            </div>
            <dl className="diagnostic-list">
              {[
                ["Policy", runtime?.alert_policy_version],
                ["Default target count", runtime?.default_target_count],
                ["Families", runtime?.family_status.length],
                ["Mechanism count", runtime?.targets.length],
                ["Exact lane IDs", runtime?.active_lane_ids.join(" · ")],
                [
                  "Mechanism IDs",
                  runtime?.targets
                    .map((target) => target.mechanism_id)
                    .filter(Boolean)
                    .join(" · "),
                ],
                ["DGA readiness", runtime?.dga_model_readiness],
                ["DGA failure reason", runtime?.dga_model_failure_reason],
                ["DGA model SHA", modelSha],
                ["Source adapters", runtime?.supported_sources.join(" · ")],
                ["Database", runtime?.database_status],
                ["Durable results", runtime?.durable_result_count],
                ["Live subscribers", runtime?.live_subscriber_count],
                ["Runtime state", runtime?.state],
              ].map(([label, value]) => (
                <div key={String(label)}>
                  <dt>{label}</dt>
                  <dd>{value ?? "Unavailable"}</dd>
                </div>
              ))}
            </dl>
            <p>
              Exact IDs and runtime values are available here for audit and
              troubleshooting.
            </p>
          </aside>
        </ModalPortal>
      )}
    </div>
  );
}

function NavIcon({ name }: { name: PageKey }) {
  const paths: Record<PageKey, string> = {
    overview: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
    replay: "M5 3v18l15-9z",
    alerts: "M12 3 3 8v8l9 5 9-5V8z M3 8l9 5 9-5 M12 13v8",
    investigations: "M7 7h10 M7 17h10 M4 12h16 M8 4l-4 3 4 3 M16 14l4 3-4 3",
    results: "M6 3h9l4 4v14H6z M15 3v5h4 M9 12h7 M9 16h7",
  };
  return (
    <svg
      viewBox="0 0 24 24"
      width="17"
      height="17"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.65"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={paths[name]} />
    </svg>
  );
}
