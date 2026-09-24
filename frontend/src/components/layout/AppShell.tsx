import type { ReactNode } from "react";
import type { PageKey } from "../../state/types";
import { useClock } from "../../hooks/useClock";
import { useEvidence } from "../../state/EvidenceContext";

const links: Array<[PageKey, string, string]> = [
  ["overview", "◫", "Overview"],
  ["alerts", "◧", "Analyst Alerts"],
  ["results", "⊞", "Evidence Results"],
  ["system", "⌘", "System & Evidence Status"],
  ["replay", "▷", "Replay"],
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
  const clock = useClock();
  const title = links.find(([key]) => key === page)?.[2] ?? "Overview";
  const badge =
    state.replay?.state === "RUNNING"
      ? "REPLAYING"
      : (state.runtime?.state ?? (state.pageError ? "OFFLINE" : "CONNECTING"));
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
            <small>OPERATIONS CONSOLE</small>
          </span>
        </a>
        <p className="nav-label">WORKSPACE</p>
        <nav className="primary-nav">
          {links.map(([key, icon, label]) => (
            <button
              type="button"
              key={key}
              data-page={key}
              onClick={() => onNavigate(key)}
              className={`nav-item${page === key ? " active" : ""}`}
              aria-current={page === key ? "page" : undefined}
            >
              <span className="nav-icon" aria-hidden="true">
                {icon}
              </span>
              {label}
              {key === "alerts" && (
                <span className="nav-count">{state.alerts.length}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-spacer" />
        <div className="sidebar-foot">
          <div className="foot-mark">SIH 26145</div>
          <p>
            Passive observation
            <br />
            Read-only evidence analysis
          </p>
          <span className="version">SIH_ALERT_POLICY_V1</span>
        </div>
      </aside>
      <div className="main-column">
        <header className="topbar">
          <div className="breadcrumbs">
            <span>EvidenceGate</span>
            <span className="crumb-slash">/</span>
            <strong>{title}</strong>
          </div>
          <div className="topbar-right">
            <span className="topbar-mode">
              <span className="mode-dot" />
              PASSIVE · READ ONLY
            </span>
            <span className="runtime-pill">
              <span
                className={`runtime-dot${badge === "OFFLINE" ? " offline" : badge === "REPLAYING" ? " replaying" : ""}`}
              />
              <strong>{badge}</strong>
            </span>
            <span className="clock">{clock}</span>
          </div>
        </header>
        <main id="main-content">
          {state.pageError && (
            <div className="stream-notice" role="status">
              {state.pageError}
            </div>
          )}
          {children}
        </main>
        <footer className="app-footer">
          <span>EvidenceGate · SIH26145</span>
          <span>
            Passive observation · Read-only analysis · Immutable result
            provenance
          </span>
        </footer>
      </div>
    </div>
  );
}
