import { useEffect, useRef, useState, type ReactNode } from "react";
import type { PageKey } from "../../state/types";
import { useClock } from "../../hooks/useClock";
import { useEvidence } from "../../state/EvidenceContext";

const links: Array<[PageKey, string, string]> = [
  ["overview", "◫", "Overview"],
  ["replay", "▷", "Traffic lab"],
  ["alerts", "◇", "Analyst queue"],
  ["investigations", "↔", "Investigations"],
  ["results", "⊞", "Evidence"],
];
export function AppShell({ page, onNavigate, children }: { page: PageKey; onNavigate: (page: PageKey) => void; children: ReactNode }) {
  const { state } = useEvidence();
  const clock = useClock();
  const [healthOpen, setHealthOpen] = useState(false);
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const healthButton = useRef<HTMLButtonElement>(null);
  const diagnosticClose = useRef<HTMLButtonElement>(null);
  const runtime = state.runtime;
  const badge = state.pageError ? "Offline" : state.replay?.state === "RUNNING" ? "Replaying" : runtime ? "Online" : "Connecting";

  useEffect(() => {
    if (!healthOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setHealthOpen(false); healthButton.current?.focus(); }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [healthOpen]);
  useEffect(() => { if (diagnosticsOpen) diagnosticClose.current?.focus(); }, [diagnosticsOpen]);

  const dgaRefs = [...state.results.values()].filter((result) => result.lane_id === "dga.m1").flatMap((result) => result.model_refs ?? []);
  const modelSha = dgaRefs.find((ref) => typeof ref === "string" && ref.startsWith("sha256:")) ?? "Unavailable from runtime status";
  return <div className="app-shell">
    <aside className="sidebar" aria-label="Primary navigation">
      <a className="brand" href="#/overview" onClick={(event) => { event.preventDefault(); onNavigate("overview"); }}>
        <span className="brand-mark" aria-hidden="true">EG</span><span><strong>EvidenceGate</strong><small>Passive network evidence</small></span>
      </a>
      <nav className="primary-nav">{links.map(([key, icon, label]) => <button type="button" key={key} data-page={key} onClick={() => onNavigate(key)} className={`nav-item${page === key ? " active" : ""}`} aria-current={page === key ? "page" : undefined}>
        <span className="nav-icon" aria-hidden="true">{icon}</span>{label}
      </button>)}</nav>
      <div className="sidebar-spacer" /><div className="sidebar-foot"><p>Passive · read-only</p></div>
    </aside>
    <div className="main-column">
      <header className="topbar"><div className="breadcrumbs"><span>EvidenceGate</span></div><div className="topbar-right">
        <span className="topbar-mode"><span className="mode-dot" />Passive · read-only</span>
        <button ref={healthButton} type="button" className="runtime-pill health-trigger" aria-expanded={healthOpen} aria-haspopup="dialog" onClick={() => setHealthOpen((open) => !open)}>
          <span className={`runtime-dot${badge === "Offline" ? " offline" : ""}`} /><strong>{badge}</strong>
        </button>
        <span className="clock">{clock}</span>
      </div>
      {healthOpen && <div className="health-popover" role="dialog" aria-label="System health" onKeyDown={(event) => { if (event.key === "Escape") { setHealthOpen(false); healthButton.current?.focus(); } }}>
        <div className="health-popover-head"><h2>System health</h2><button aria-label="Close system health" onClick={() => { setHealthOpen(false); healthButton.current?.focus(); }}>×</button></div>
        <dl>
          <div><dt>Runtime</dt><dd>{badge}</dd></div>
          <div><dt>Analytics</dt><dd>{runtime ? runtime.targets.length : 0} registered</dd></div>
          <div><dt>Evidence store</dt><dd>{runtime?.database_status === "connected" ? "Available" : "Checking"}</dd></div>
          <div><dt>Input</dt><dd>{state.replay?.state === "RUNNING" ? state.replay.source_type ?? "Replay" : "Controlled replay"}</dd></div>
        </dl>
        <button className="text-button" onClick={() => { setHealthOpen(false); setDiagnosticsOpen(true); }}>Technical details →</button>
      </div>}</header>
      <main id="main-content">{(state.pageError || state.streamState === "reconnecting") && <div className="connection-notice" role="status"><strong>{state.pageError ? "Unable to reach EvidenceGate" : "Reconnecting to the service"}</strong><span>Previously captured evidence remains available if already loaded. Check backend connectivity if this persists.</span></div>}{children}</main>
    </div>
    {diagnosticsOpen && <>
      <button className="drawer-backdrop" aria-label="Close system diagnostics" onClick={() => setDiagnosticsOpen(false)} />
      <aside className="diagnostics-drawer" role="dialog" aria-modal="true" aria-labelledby="diagnostics-title" onKeyDown={(event) => { if (event.key === "Escape") { setDiagnosticsOpen(false); healthButton.current?.focus(); } }}>
        <div className="inspector-head"><div><span className="eyebrow">System diagnostics</span><h2 id="diagnostics-title">Technical details</h2></div><button ref={diagnosticClose} className="inspector-close" aria-label="Close diagnostics" onClick={() => { setDiagnosticsOpen(false); healthButton.current?.focus(); }}>×</button></div>
        <dl className="diagnostic-list">{[
          ["Policy", runtime?.alert_policy_version], ["Default target count", runtime?.default_target_count], ["Families", runtime?.family_status.length], ["Mechanism count", runtime?.targets.length], ["Exact lane IDs", runtime?.active_lane_ids.join(" · ")], ["Mechanism IDs", runtime?.targets.map((target) => target.mechanism_id).filter(Boolean).join(" · ")], ["DGA readiness", runtime?.dga_model_readiness], ["DGA failure reason", runtime?.dga_model_failure_reason], ["DGA model SHA", modelSha], ["Source adapters", runtime?.supported_sources.join(" · ")], ["Database", runtime?.database_status], ["Durable results", runtime?.durable_result_count], ["Live subscribers", runtime?.live_subscriber_count], ["Runtime state", runtime?.state],
        ].map(([label, value]) => <div key={String(label)}><dt>{label}</dt><dd>{value ?? "Unavailable"}</dd></div>)}</dl>
        <p>Exact IDs and runtime values are available here for audit and troubleshooting.</p>
      </aside>
    </>}
  </div>;
}
