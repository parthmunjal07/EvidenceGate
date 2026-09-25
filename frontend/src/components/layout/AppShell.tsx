import type { ReactNode } from "react";
import type { PageKey } from "../../state/types";
import { useClock } from "../../hooks/useClock";
import { useEvidence } from "../../state/EvidenceContext";

const links: Array<[PageKey, string, string]> = [
  ["overview", "◫", "Overview"],
  ["alerts", "◧", "Analyst alerts"],
  ["results", "⊞", "Evidence results"],
  ["system", "⌘", "System status"],
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
  const badge =
    state.replay?.state === "RUNNING"
      ? "Replaying"
      : (state.runtime?.state === "ONLINE" ? "Online" : state.pageError ? "Offline" : state.runtime ? "Replaying" : "Connecting");
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
            <small>Passive network evidence</small>
          </span>
        </a>
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
          <div className="foot-mark">SIH26145</div>
          <p>Passive · read-only</p>
        </div>
      </aside>
      <div className="main-column">
        <header className="topbar">
          <div className="breadcrumbs">
            <span>EvidenceGate</span>
          </div>
          <div className="topbar-right">
            <span className="topbar-mode">
              <span className="mode-dot" />
              Passive · read-only
            </span>
            <span className="runtime-pill">
              <span
                className={`runtime-dot${badge === "Offline" ? " offline" : badge === "Replaying" ? " replaying" : ""}`}
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
          <span>SIH26145 · Passive, read-only</span>
          <span>Policy: {state.runtime?.alert_policy_version ?? "Unavailable"}</span>
        </footer>
      </div>
    </div>
  );
}
