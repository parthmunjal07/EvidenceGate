(() => {
  "use strict";

  const state = {
    runtime: null,
    results: new Map(),
    alerts: [],
    statusItems: [],
    resultCursor: null,
    syncCursor: null,
    selectedAlert: null,
    selectedResult: null,
    replay: null,
  };
  const $ = (id) => document.getElementById(id);
  const pretty = (value) => JSON.stringify(value ?? null, null, 2);
  const readable = (value) => String(value ?? "—").replaceAll("_", " ").toLowerCase();
  const time = (value) => value ? new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "medium" }) : "—";
  const shortTime = (value) => value ? new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "—";
  const qualityLabel = (quality) => {
    const values = [quality?.packet_loss, quality?.sampling, quality?.parser, quality?.capture_gap];
    if (values.includes("DEGRADED")) return "Degraded";
    if (values.every((value) => value === "CLEAR")) return "Clear";
    return "Unknown";
  };
  const visCount = (visibility) => (visibility?.available || []).length;

  async function request(url, options) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
    return data;
  }
  function addText(parent, tag, className, value) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    node.textContent = value ?? "—";
    parent.append(node);
    return node;
  }
  function addPair(parent, label, value, className = "") {
    const wrapper = document.createElement("div");
    wrapper.className = `inspect-pair ${className}`.trim();
    addText(wrapper, "dt", "", label);
    const dd = document.createElement("dd");
    if (value instanceof Node) dd.append(value);
    else dd.textContent = value ?? "—";
    wrapper.append(dd);
    parent.append(wrapper);
    return wrapper;
  }
  function evidenceSummary(evidence) {
    if (evidence?.evidence_kind === "DGA_LEXICAL_MODEL_EVIDENCE") {
      const score = evidence.dga_labelled_lexical_resemblance_score;
      return score === undefined ? "DGA lexical model evidence" : `DGA-labelled lexical resemblance score ${Number(score).toFixed(3)}`;
    }
    const pairs = Object.entries(evidence || {}).slice(0, 2);
    return pairs.length ? pairs.map(([key, value]) => `${key.replaceAll("_", " ")}: ${typeof value === "object" ? "…" : value}`).join(" · ") : "Structured evidence available";
  }
  function confidenceSummary(alert) {
    if (alert.confidence_basis === "MODEL_SCORE") {
      const value = alert.confidence_score;
      return `DGA-labelled lexical resemblance score: ${value == null ? "not present" : Number(value).toFixed(6)}. Not calibrated attack probability.`;
    }
    return `${alert.confidence_basis}: ${alert.confidence_statement}. Numeric attack probability: not defined by this analytic.`;
  }
  function modelShortLabel(refs) {
    const model = (refs || []).find((value) => value.startsWith("model:DGA-A1-M1-R1"));
    const hash = (refs || []).find((value) => value.startsWith("sha256:"));
    if (!model) return "";
    const digest = hash ? ` · ${hash.slice(0, 15)}…${hash.slice(-6)}` : "";
    return `${model.replace("model:", "")} ${digest}`.trim();
  }

  function navigate(page) {
    document.querySelectorAll(".page").forEach((node) => node.classList.toggle("active-page", node.id === `page-${page}`));
    document.querySelectorAll("[data-page]").forEach((node) => {
      const active = node.dataset.page === page;
      node.classList.toggle("active", active);
      if (active) node.setAttribute("aria-current", "page");
      else node.removeAttribute("aria-current");
    });
    $("page-breadcrumb").textContent = ({ overview: "Overview", alerts: "Analyst Alerts", results: "Evidence Results", system: "System & Evidence Status", replay: "Replay" }[page]);
    history.replaceState(null, "", `#${page}`);
    window.scrollTo({ top: 0, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
  }
  document.querySelectorAll("[data-page]").forEach((button) => button.addEventListener("click", () => navigate(button.dataset.page)));
  document.querySelectorAll("[data-go]").forEach((button) => button.addEventListener("click", () => navigate(button.dataset.go)));
  document.querySelector("[data-page-link]").addEventListener("click", (event) => { event.preventDefault(); navigate("overview"); });
  if (location.hash.slice(1) && $(`page-${location.hash.slice(1)}`)) navigate(location.hash.slice(1));
  setInterval(() => { $("clock").textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }); }, 1000);

  function setRuntimeBadge(runtimeState, connected = true) {
    $("runtime-state").textContent = runtimeState || "OFFLINE";
    $("runtime-dot").classList.toggle("offline", !connected);
    $("runtime-dot").classList.toggle("replaying", runtimeState === "REPLAYING");
  }
  function setMetric(id, value) { $(id).textContent = String(value); }
  function renderOperationalMetrics() {
    if (!state.runtime) return;
    const replay = state.replay || state.runtime.replay;
    setMetric("metric-input-state", replay?.state === "RUNNING" ? "REPLAYING" : state.runtime.state);
    $("metric-input-detail").textContent = replay?.scenario
      ? `${replay.source_type || "Source"} · ${replay.scenario}`
      : `${state.runtime.default_target_count} targets ready · ${state.runtime.scenarios.length} replay scenarios`;
    setMetric("metric-alerts", state.alerts.length);
    const degraded = state.statusItems.filter((item) => item.result_type === "QUALITY_DEGRADED").length;
    setMetric("metric-quality", degraded);
    $("metric-status-detail").textContent = `Evidence status records: ${state.statusItems.length}`;
    const unavailable = state.statusItems.filter((item) => item.result_type === "ANALYTIC_UNAVAILABLE").length;
    setMetric("metric-unavailable", unavailable);
    $("metric-target-detail").textContent = `Across ${state.runtime.default_target_count} registered targets`;
    $("nav-alert-count").textContent = String(state.alerts.length);
  }

  function activateFlow(laneId = "", resultType = "") {
    const alertProjection = resultType === "REVIEW_FINDING";
    const statusProjection = ["QUALITY_DEGRADED", "PREREQUISITE_MISSING", "INSUFFICIENT_EVIDENCE", "ANALYTIC_UNAVAILABLE", "PLUGIN_STATUS"].includes(resultType);
    const outcomeStage = alertProjection ? "projection" : statusProjection ? "status" : null;
    document.querySelectorAll(".flow-stage").forEach((node) => node.classList.remove("is-active", "is-presentation"));
    const stages = ["observation", "quality", "router", "analytics", "results", ...(outcomeStage ? [outcomeStage] : [])];
    stages.forEach((name, index) => {
      const stage = document.querySelector(`[data-stage="${name}"]`);
      if (stage) setTimeout(() => stage.classList.add(name === "projection" || name === "status" ? "is-presentation" : "is-active"), index * 170);
    });
    const pulse = $("flow-pulse");
    if (pulse && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
      pulse.getAnimations().forEach((animation) => animation.cancel());
      pulse.setAttribute("cx", "82");
      const frames = [{ transform: "translate(0px,0px)" }, { transform: "translate(225px,0px)" }, { transform: "translate(430px,0px)" }, { transform: "translate(640px,0px)" }, { transform: "translate(840px,0px)" }, ...(outcomeStage ? [{ transform: `translate(894px,${alertProjection ? "-27px" : "75px"})` }] : [])];
      pulse.animate(frames, { duration: 1900, easing: "ease-in-out" });
    }
    const presentation = alertProjection ? "SIH alert projection" : statusProjection ? "evidence status projection" : "no SIH projection";
    $("flow-state").textContent = `${laneId || "Persisted result"} · ${presentation}`;
    $("flow-event-detail").textContent = laneId ? `Persisted result received for ${laneId}.` : "Persisted result notification received.";
  }
  function addReplayLog(result) {
    const host = $("replay-event-log");
    const empty = host.querySelector(".log-empty");
    if (empty) empty.remove();
    const item = document.createElement("div");
    item.className = "event-log-item";
    addText(item, "time", "", shortTime(result.created_time));
    addText(item, "strong", "", result.lane_id);
    addText(item, "span", "", `${readable(result.result_type)} · ${result.mechanism_id || result.lane_id}`);
    host.prepend(item);
    while (host.children.length > 8) host.lastElementChild.remove();
  }

  function renderOverviewAlerts() {
    const rows = $("overview-alert-rows");
    rows.replaceChildren();
    const recent = state.alerts.slice(0, 6);
    $("overview-empty").hidden = recent.length > 0;
    for (const alert of recent) {
      const tr = document.createElement("tr");
      tr.className = "selectable-row";
      tr.tabIndex = 0;
      const values = [shortTime(alert.timestamp), alert.threat_class, alert.mechanism_id, alert.entity_or_flow_reference, evidenceSummary(alert.supporting_evidence?.structured), alert.confidence_basis, qualityLabel(alert.quality)];
      if (alert.confidence_basis === "MODEL_SCORE") values[4] += ` · ${modelShortLabel(alert.model_refs)}`;
      values.forEach((value, index) => addText(tr, "td", index === 4 ? "evidence-cell" : "", value));
      const action = document.createElement("td");
      addText(action, "span", "row-arrow", "→");
      tr.append(action);
      tr.addEventListener("click", () => { navigate("alerts"); selectAlert(alert); });
      tr.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); tr.click(); } });
      rows.append(tr);
    }
  }

  function alertMatches(alert) {
    const term = $("alert-search").value.trim().toLowerCase();
    const classValue = $("alert-class-filter").value;
    const basisValue = $("alert-basis-filter").value;
    const searchable = [alert.threat_class, alert.mechanism_id, alert.entity_or_flow_reference, evidenceSummary(alert.supporting_evidence?.structured), alert.source_result_ids.join(" ")].join(" ").toLowerCase();
    const qualityValue = $("alert-quality-filter").value;
    const visibilityValue = $("alert-visibility-filter").value;
    const visibility = alert.visibility || {};
    return (!term || searchable.includes(term)) && (!classValue || alert.threat_class === classValue)
      && (!basisValue || alert.confidence_basis === basisValue)
      && (!qualityValue || qualityLabel(alert.quality) === qualityValue)
      && (!visibilityValue || (visibility[visibilityValue] || []).length > 0);
  }
  function renderAlerts() {
    const rows = $("alert-rows");
    rows.replaceChildren();
    const filtered = state.alerts.filter(alertMatches);
    $("alert-result-total").textContent = `${filtered.length} records`;
    $("alert-empty").hidden = filtered.length > 0;
    for (const alert of filtered) {
      const tr = document.createElement("tr");
      tr.className = `selectable-row${state.selectedAlert?.alert_id === alert.alert_id ? " selected" : ""}`;
      tr.tabIndex = 0;
      const visibility = `${visCount(alert.visibility)} available`;
      const values = [shortTime(alert.timestamp), alert.threat_class, alert.mechanism_id, alert.entity_or_flow_reference, evidenceSummary(alert.supporting_evidence?.structured), alert.confidence_basis, qualityLabel(alert.quality), visibility, "Review"];
      if (alert.confidence_basis === "MODEL_SCORE") values[4] += ` · ${modelShortLabel(alert.model_refs)}`;
      values.forEach((value, index) => addText(tr, "td", index === 4 ? "evidence-cell" : index === 8 ? "priority-text" : "", value));
      tr.addEventListener("click", () => selectAlert(alert));
      tr.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); tr.click(); } });
      rows.append(tr);
    }
  }
  function section(parent, title, description = "") {
    const block = document.createElement("section");
    block.className = "inspect-section";
    const head = document.createElement("div");
    head.className = "inspect-section-head";
    addText(head, "h3", "", title);
    if (description) addText(head, "span", "", description);
    block.append(head);
    parent.append(block);
    return block;
  }
  function codeBlock(parent, label, value) {
    const block = document.createElement("div");
    block.className = "code-field";
    addText(block, "span", "field-label", label);
    const pre = document.createElement("pre");
    pre.textContent = typeof value === "string" ? value : pretty(value);
    block.append(pre);
    parent.append(block);
    return block;
  }
  function snapshotRows(parent, label, snapshot, kind) {
    const host = document.createElement("div");
    host.className = "snapshot-list";
    addText(host, "span", "field-label", label);
    if (kind === "visibility") {
      for (const [key, symbol, title] of [
        ["available", "✓", "Available"], ["unavailable", "×", "Unavailable"], ["degraded", "!", "Degraded"],
      ]) {
        const row = document.createElement("div"); row.className = "snapshot-row";
        addText(row, "span", "snapshot-state", `${symbol} ${title}`);
        addText(row, "span", "snapshot-values", (snapshot?.[key] || []).join(" · ") || "None reported");
        host.append(row);
      }
    } else {
      for (const [key, value] of Object.entries(snapshot || {})) {
        const row = document.createElement("div"); row.className = "snapshot-row";
        const stateValue = String(value ?? "UNKNOWN");
        const symbol = stateValue === "CLEAR" ? "✓" : stateValue === "DEGRADED" ? "!" : "○";
        addText(row, "span", "snapshot-state", `${symbol} ${key.replaceAll("_", " ")}`);
        addText(row, "span", "snapshot-values", stateValue.replaceAll("_", " "));
        host.append(row);
      }
    }
    parent.append(host);
    return host;
  }
  function sourceLinks(ids) {
    const wrap = document.createElement("div");
    wrap.className = "source-links";
    (ids || []).forEach((id) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "inline-link source-link";
      button.textContent = id;
      button.addEventListener("click", async () => {
        try {
          let result = state.results.get(id);
          if (!result) result = await request(`/results/${encodeURIComponent(id)}`);
          state.results.set(id, result);
          navigate("results");
          selectResult(result);
        } catch (error) { showNotice(error.message); }
      });
      wrap.append(button);
    });
    return wrap;
  }
  function renderAlertInspector(alert) {
    const panel = $("alert-inspector");
    panel.replaceChildren();
    panel.classList.add("has-selection");
    inspectorHeader(panel, "ANALYST ATTENTION RECORD", alert.threat_class, alert.mechanism_id);
    const identity = section(panel, "Identity");
    const identityList = document.createElement("dl");
    identityList.className = "inspect-list";
    addPair(identityList, "Entity / flow", alert.entity_or_flow_reference);
    addPair(identityList, "Timestamp", time(alert.timestamp));
    addPair(identityList, "Priority", "Review · analyst attention");
    addPair(identityList, "Result type", readable(alert.result_type));
    identity.append(identityList);
    const ev = section(panel, "Supporting evidence");
    addText(ev, "p", "inspect-summary", evidenceSummary(alert.supporting_evidence?.structured));
    codeBlock(ev, "STRUCTURED EVIDENCE", alert.supporting_evidence?.structured);
    codeBlock(ev, "EVIDENCE ITEMS", alert.supporting_evidence?.evidence_items || []);
    addPair(ev, "Source observation IDs", (alert.supporting_evidence?.source_observation_ids || []).join(" · ") || "None supplied");
    const confidence = section(panel, "Confidence semantics");
    const score = document.createElement("div");
    score.className = "confidence-note";
    addText(score, "strong", "", confidenceSummary(alert));
    if (alert.confidence_basis === "MODEL_SCORE") addText(score, "p", "", "This lexical resemblance score is not calibrated attack probability.");
    confidence.append(score);
    const context = section(panel, "Visibility & quality");
    snapshotRows(context, "VISIBILITY CLASSES", alert.visibility, "visibility");
    snapshotRows(context, "SOURCE QUALITY FACTS", alert.quality, "quality");
    const claim = section(panel, "Claim ceiling");
    addText(claim, "p", "claim-text", alert.claim_ceiling);
    const prov = section(panel, "Governance & provenance");
    const provList = document.createElement("dl");
    provList.className = "inspect-list";
    addPair(provList, "Governing decision IDs", (alert.governing_ids || []).join(" · ") || "None supplied");
    addPair(provList, "Model refs", (alert.model_refs || []).join(" · ") || "Not applicable");
    addPair(provList, "Parser refs", (alert.parser_refs || []).join(" · ") || "None supplied");
    addPair(provList, "Provenance refs", (alert.provenance_refs || []).join(" · ") || "None supplied");
    addPair(provList, "Quality refs", (alert.quality_refs || []).join(" · ") || "None supplied");
    addPair(provList, "Source result ID", sourceLinks(alert.source_result_ids));
    prov.append(provList);
    setInspectorSelected("alert-inspector", true);
  }
  function inspectorHeader(panel, kicker, title, subtitle) {
    const header = document.createElement("header");
    header.className = "inspector-head";
    const titleWrap = document.createElement("div");
    addText(titleWrap, "p", "eyebrow", kicker);
    addText(titleWrap, "h2", "", title);
    addText(titleWrap, "p", "inspector-subtitle", subtitle);
    const close = document.createElement("button");
    close.type = "button";
    close.className = "inspector-close";
    close.setAttribute("aria-label", "Close inspector");
    close.textContent = "×";
    close.addEventListener("click", closeInspectors);
    header.append(titleWrap, close);
    panel.append(header);
  }
  function setInspectorSelected(id, selected) {
    document.querySelectorAll(`#${id} tbody tr`).forEach((row) => row.classList.toggle("selected", selected && row.classList.contains("selected")));
    if (selected && matchMedia("(max-width: 1120px)").matches) {
      $("inspector-backdrop").hidden = false;
      document.body.classList.add("inspector-open");
    }
  }
  function selectAlert(alert) {
    state.selectedAlert = alert;
    state.selectedResult = null;
    renderAlerts();
    renderAlertInspector(alert);
  }

  function resultMatches(result) {
    const term = $("result-search").value.trim().toLowerCase();
    const family = $("result-family-filter").value;
    const type = $("result-type-filter").value;
    const searchable = [result.entity_reference, result.lane_id, result.mechanism_id, result.result_id, result.family, evidenceSummary(result.evidence)].join(" ").toLowerCase();
    return (!term || searchable.includes(term)) && (!family || result.family === family) && (!type || result.result_type === type);
  }
  function renderResults() {
    const rows = $("result-rows");
    rows.replaceChildren();
    const items = [...state.results.values()].filter(resultMatches).sort((a, b) => b.created_time.localeCompare(a.created_time) || b.result_id.localeCompare(a.result_id));
    $("result-total").textContent = `${items.length} records`;
    $("result-empty").hidden = items.length > 0;
    for (const result of items) {
      const tr = document.createElement("tr");
      tr.className = `selectable-row${state.selectedResult?.result_id === result.result_id ? " selected" : ""}`;
      tr.tabIndex = 0;
      const summary = `${evidenceSummary(result.evidence)}${result.lane_id === "dga.m1" ? ` · ${modelShortLabel(result.model_refs)}` : ""}`;
      const values = [shortTime(result.created_time), result.family, result.lane_id, result.mechanism_id || "—", readable(result.result_type), result.entity_reference, summary, qualityLabel(result.quality_snapshot), `${visCount(result.visibility_snapshot)} available`];
      values.forEach((value, index) => addText(tr, "td", index === 6 ? "evidence-cell" : "", value));
      tr.addEventListener("click", () => selectResult(result));
      tr.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); tr.click(); } });
      rows.append(tr);
    }
  }
  function renderResultInspector(result) {
    const panel = $("result-inspector");
    panel.replaceChildren();
    panel.classList.add("has-selection");
    inspectorHeader(panel, "IMMUTABLE SCIENTIFIC RESULT", result.result_type.replaceAll("_", " "), `${result.family} · ${result.lane_id}`);
    const identity = section(panel, "Identity");
    const list = document.createElement("dl"); list.className = "inspect-list";
    addPair(list, "Result ID", result.result_id);
    addPair(list, "Timestamp", time(result.created_time));
    addPair(list, "Lane / mechanism", `${result.lane_id} / ${result.mechanism_id || "—"}`);
    addPair(list, "Scientific status", result.status_snapshot?.scientific_status);
    addPair(list, "Integration status", result.status_snapshot?.integration_status);
    addPair(list, "Readiness", result.status_snapshot?.readiness);
    addPair(list, "Governance version", result.status_snapshot?.governance_version);
    addPair(list, "Quality degraded", result.status_snapshot?.quality_degraded ? "Yes" : "No");
    identity.append(list);
    const facts = section(panel, "Observed facts");
    addPair(facts, "Entity / flow", result.entity_reference);
    addPair(facts, "Source observation IDs", (result.source_observation_ids || []).join(" · ") || "None supplied");
    addPair(facts, "Evidence interval", result.evidence_interval ? result.evidence_interval.map(time).join(" — ") : "Not specified");
    const evidence = section(panel, "Derived evidence");
    addText(evidence, "p", "inspect-summary", evidenceSummary(result.evidence));
    codeBlock(evidence, "STRUCTURED EVIDENCE", result.evidence);
    if (result.evidence_items?.length) codeBlock(evidence, "EVIDENCE ITEMS", result.evidence_items);
    const confidence = section(panel, "Confidence semantics");
    if (result.lane_id === "dga.m1") {
      const score = result.evidence?.dga_labelled_lexical_resemblance_score;
      addText(confidence, "p", "confidence-note", `DGA-labelled lexical resemblance score: ${score == null ? "not supplied" : Number(score).toFixed(6)}. Not calibrated attack probability.`);
    } else addText(confidence, "p", "confidence-note", "Numeric attack probability: not defined by this analytic.");
    const conditions = section(panel, "Visibility & quality");
    snapshotRows(conditions, "VISIBILITY CLASSES", result.visibility_snapshot, "visibility");
    snapshotRows(conditions, "SOURCE QUALITY FACTS", result.quality_snapshot, "quality");
    const missing = section(panel, "Missing evidence & prerequisites");
    codeBlock(missing, "MISSING PREREQUISITES", result.missing_prerequisites || []);
    const claim = section(panel, "Claim ceiling");
    addText(claim, "p", "claim-text", result.claim_ceiling);
    const provenance = section(panel, "Model, parser & governing references");
    const p = document.createElement("dl"); p.className = "inspect-list";
    addPair(p, "Model refs", (result.model_refs || []).join(" · ") || "None supplied");
    addPair(p, "Parser refs", (result.parser_refs || []).join(" · ") || "None supplied");
    addPair(p, "Provenance refs", (result.provenance_refs || []).join(" · ") || "None supplied");
    addPair(p, "Quality refs", (result.quality_refs || []).join(" · ") || "None supplied");
    addPair(p, "Source observation IDs", (result.source_observation_ids || []).join(" · ") || "None supplied");
    addPair(p, "Source IDs", (result.source_ids || []).join(" · ") || "None supplied");
    addPair(p, "Governing decision IDs", (result.governing_ids || []).join(" · ") || "None supplied");
    addPair(p, "Config hash", result.config_hash || "Not supplied");
    addPair(p, "State version", result.state_version ?? "Not supplied");
    addPair(p, "Source result IDs", sourceLinks([result.result_id]));
    provenance.append(p);
    setInspectorSelected("result-inspector", true);
  }
  function selectResult(result) {
    state.selectedResult = result;
    state.selectedAlert = null;
    renderResults();
    renderResultInspector(result);
  }
  function closeInspectors() {
    document.body.classList.remove("inspector-open");
    $("inspector-backdrop").hidden = true;
    state.selectedAlert = null;
    state.selectedResult = null;
    resetInspector("alert-inspector", "⌕", "Select an alert", "Choose a row to inspect its evidence, confidence meaning, visibility, quality, and source result.");
    resetInspector("result-inspector", "⊞", "Select a result", "Inspect observed facts, derived evidence, missing prerequisites, claim ceiling, and provenance.");
    renderAlerts();
    renderResults();
  }
  function resetInspector(id, glyph, title, description) {
    const panel = $(id);
    panel.classList.remove("has-selection");
    panel.replaceChildren();
    const placeholder = document.createElement("div");
    placeholder.className = "inspector-placeholder";
    addText(placeholder, "span", "inspect-glyph", glyph);
    addText(placeholder, "strong", "", title);
    addText(placeholder, "p", "", description);
    panel.append(placeholder);
  }
  $("inspector-backdrop").addEventListener("click", closeInspectors);
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeInspectors(); });

  function renderStatusRecords() {
    const host = $("status-records"); host.replaceChildren();
    $("status-record-total").textContent = `${state.statusItems.length} records`;
    if (!state.statusItems.length) { addText(host, "div", "empty-state", "No system or evidence status records in the current result window."); return; }
    for (const item of state.statusItems) {
      const article = document.createElement("article"); article.className = "status-record";
      const top = document.createElement("div"); top.className = "status-record-head";
      addText(top, "span", `status-priority ${item.priority.toLowerCase()}`, item.priority);
      const title = document.createElement("strong"); title.textContent = `${readable(item.status_kind)} · ${item.mechanism_id}`;
      addText(top, "time", "", time(item.timestamp));
      article.append(top, title);
      addText(article, "p", "status-entity", item.entity_or_flow_reference);
      const note = document.createElement("dl"); note.className = "inspect-list status-record-grid";
      addPair(note, "Result type", readable(item.result_type));
      addPair(note, "Missing prerequisites", (item.missing_prerequisites || []).join(" · ") || "None supplied");
      addPair(note, "Visibility", pretty(item.visibility));
      addPair(note, "Quality", pretty(item.quality));
      article.append(note);
      const claim = document.createElement("details"); claim.className = "status-claim";
      addText(claim, "summary", "", "Claim ceiling and supporting evidence");
      codeBlock(claim, "CLAIM CEILING", item.claim_ceiling);
      codeBlock(claim, "SUPPORTING EVIDENCE", item.supporting_evidence);
      article.append(claim);
      const links = document.createElement("div"); links.className = "status-sources"; addText(links, "span", "field-label", "SOURCE RESULTS"); links.append(sourceLinks(item.source_result_ids)); article.append(links);
      host.append(article);
    }
  }
  function renderSystem(runtime) {
    const replay = state.replay || runtime.replay;
    const summary = $("system-summary"); summary.replaceChildren();
    const cards = [
      ["Runtime", runtime.state, runtime.state === "ONLINE" ? "connected" : "replaying"],
      ["Database", runtime.database_status, "connected"],
      ["Alert policy", runtime.alert_policy_version || "Unavailable", runtime.alert_policy_active ? "active" : "inactive"],
      ["Default targets", runtime.default_target_count, "registered"],
      ["DGA model", runtime.dga_model_readiness, runtime.dga_model_readiness === "VERIFIED_READY" ? "verified" : "readiness issue"],
      ["Active ML", "DGA-A1/M1-R1", "only active ML"],
      ["Input source", replay?.source_type || "No replay source", replay?.scenario || "idle"],
      ["Live subscribers", runtime.live_subscriber_count, "event streams"],
    ];
    cards.forEach(([label, value, detail]) => { const card = document.createElement("article"); card.className = "system-card"; addText(card, "span", "metric-label", label); addText(card, "strong", "system-value", value); addText(card, "small", "", detail); summary.append(card); });
    const groups = $("target-groups"); groups.replaceChildren();
    const grouped = new Map();
    for (const target of runtime.targets) {
      const family = target.lane_id.split(".")[0];
      if (!grouped.has(family)) grouped.set(family, []);
      grouped.get(family).push(target);
    }
    $("target-count-badge").textContent = `${runtime.default_target_count} targets`;
    for (const [family, targets] of grouped) {
      const group = document.createElement("section"); group.className = "target-group";
      const title = family === "dns_tunnelling" ? "DNS Tunnelling" : family === "encrypted_session" ? "Encrypted Sessions" : family === "unusual_transfer" ? "Unusual Transfer" : family.toUpperCase();
      addText(group, "h3", "", title);
      for (const target of targets) {
        const row = document.createElement("div"); row.className = "target-row";
        addText(row, "code", "lane-name", target.lane_id);
        addText(row, "span", "target-mechanism", target.mechanism_id || "No mechanism ID");
        const status = target.implementation === "REGISTERED_SHELL" ? "Registered shell" : target.implementation === "ACTIVE_LEXICAL_MODEL_LANE" ? "Active lexical model lane" : "Active factual mechanism";
        addText(row, "span", `target-status ${target.implementation === "REGISTERED_SHELL" ? "shell" : "active"}`, status);
        group.append(row);
      }
      groups.append(group);
    }
    $("system-refresh").textContent = `Runtime read ${new Date().toLocaleTimeString()}`;
    renderStatusRecords();
  }

  function renderReplayScenarios(runtime) {
    const host = $("replay-scenarios"); host.replaceChildren();
    for (const scenario of runtime.scenarios) {
      const card = document.createElement("article"); card.className = "scenario-card";
      const label = document.createElement("div"); label.className = "scenario-title";
      addText(label, "span", "scenario-icon", "▷");
      const names = document.createElement("div"); addText(names, "h3", "", scenario.label); addText(names, "p", "", `${scenario.family} · ${scenario.source_type}`); label.append(names); card.append(label);
      addText(card, "code", "scenario-id", scenario.id);
      const run = document.createElement("button"); run.type = "button"; run.className = "primary-button run-replay"; run.textContent = "Run replay";
      run.addEventListener("click", () => startReplay(scenario)); card.append(run); host.append(card);
    }
    if (!runtime.scenarios.length) addText(host, "div", "empty-state", "No allowlisted replay scenarios are available.");
  }
  function renderReplayStatus(replay) {
    state.replay = replay;
    const running = replay.state === "RUNNING";
    $("replay-state-title").textContent = running ? `Replaying ${replay.scenario}` : replay.state === "FAILED" ? "Replay failed" : replay.state === "COMPLETED" ? `Completed ${replay.scenario}` : "No replay is running";
    const chip = $("replay-state-chip"); chip.textContent = replay.state; chip.className = `status-chip ${running ? "running" : replay.state === "FAILED" ? "warning" : "neutral"}`;
    const bar = $("replay-progress-bar"); bar.classList.toggle("indeterminate", running); bar.style.width = running ? "35%" : replay.state === "COMPLETED" ? "100%" : "0%";
    const counters = $("replay-counters"); counters.replaceChildren();
    [["Source", replay.source_type || "—"], ["Records read", replay.records_read], ["Observations emitted", replay.observations_emitted], ["Results persisted", replay.results_persisted], ["Elapsed", `${Number(replay.elapsed_wall_seconds || 0).toFixed(2)} s`]].forEach(([label, value]) => { const item = document.createElement("div"); addText(item, "span", "field-label", label); addText(item, "strong", "", value); counters.append(item); });
    $("replay-message").textContent = replay.error || (running ? "Replay is processing source records. Persisted results will appear as they arrive." : replay.state === "COMPLETED" ? `Replay finished at ${time(replay.finished_at)}. Results remain available in Evidence Results.` : "Select an allowlisted scenario to begin.");
    renderOperationalMetrics();
    document.querySelectorAll(".run-replay").forEach((button) => { button.disabled = running; button.textContent = running ? "Replay running…" : "Run replay"; });
    setRuntimeBadge(running ? "REPLAYING" : "ONLINE", true);
    if (running) {
      document.querySelectorAll(".flow-stage").forEach((stage) => stage.classList.add("replay-ready"));
      $("flow-state").textContent = "Replay running · waiting for persisted result events";
    } else document.querySelectorAll(".flow-stage").forEach((stage) => stage.classList.remove("replay-ready"));
    renderSystem(state.runtime);
  }
  async function startReplay(scenario) {
    try {
      const speed = Number($("replay-speed").value);
      await request("/replay", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scenario: scenario.id, speed }) });
      navigate("replay");
      await monitorReplay();
    } catch (error) { $("replay-message").textContent = error.message; }
  }
  async function monitorReplay() {
    try {
      const replay = await request("/replay/status");
      renderReplayStatus(replay);
      if (replay.state === "RUNNING") setTimeout(monitorReplay, 300);
      else await refreshRuntime();
    } catch (error) { $("replay-message").textContent = error.message; }
  }

  function renderFilterOptions() {
    const classes = [...new Set(state.alerts.map((alert) => alert.threat_class))].sort();
    const classFilter = $("alert-class-filter");
    const selectedClass = classFilter.value;
    classFilter.replaceChildren(new Option("All classes", ""));
    classes.forEach((value) => classFilter.add(new Option(value.replaceAll("_", " "), value)));
    classFilter.value = selectedClass;
    const families = [...new Set([...state.results.values()].map((result) => result.family))].sort();
    const select = $("result-family-filter"); const selected = select.value;
    select.replaceChildren(new Option("All families", ""));
    families.forEach((value) => select.add(new Option(value, value)));
    select.value = selected;
  }
  function renderAll() {
    renderFilterOptions();
    renderAlerts();
    renderOverviewAlerts();
    renderResults();
    renderStatusRecords();
    renderOperationalMetrics();
    $("last-updated").textContent = `Updated ${new Date().toLocaleTimeString()}`;
  }
  async function loadAlerts() {
    if (!state.runtime?.alert_projection_available) return;
    const response = await request("/alerts?limit=500");
    state.alerts = response.alerts || [];
    state.statusItems = response.status_items || [];
    $("alert-policy-state").textContent = `${response.policy_version} · ${response.policy_status}`;
    renderAll();
  }
  async function initialLoad() {
    const page = await request("/results?limit=100");
    absorb(page.results, false);
    state.resultCursor = page.next_cursor;
    state.syncCursor = page.sync_cursor;
    $("load-more").hidden = !state.resultCursor;
  }
  function absorb(results, animate = true) {
    for (const result of results || []) {
      const isNew = !state.results.has(result.result_id);
      state.results.set(result.result_id, result);
      if (isNew && animate) {
        activateFlow(result.lane_id, result.result_type);
        addReplayLog(result);
      }
    }
    if (state.runtime) state.runtime.durable_result_count = Math.max(state.runtime.durable_result_count || 0, state.results.size);
    renderResults();
    renderOverviewAlerts();
  }
  async function loadOlder() {
    if (!state.resultCursor) return;
    const page = await request(`/results?limit=100&cursor=${encodeURIComponent(state.resultCursor)}`);
    absorb(page.results, false);
    state.resultCursor = page.next_cursor;
    $("load-more").hidden = !state.resultCursor;
  }
  async function resync() {
    if (!state.syncCursor) await initialLoad();
    else {
      let cursor = state.syncCursor;
      while (true) {
        const page = await request(`/results?limit=500&cursor=${encodeURIComponent(cursor)}`);
        absorb(page.results, true);
        if (page.sync_cursor) state.syncCursor = page.sync_cursor;
        if (page.results.length < 500) break;
        cursor = page.next_cursor;
      }
    }
    await loadAlerts();
  }
  async function refreshRuntime() {
    state.runtime = await request("/runtime");
    state.replay = state.runtime.replay;
    setRuntimeBadge(state.runtime.state, true);
    renderOperationalMetrics();
    renderSystem(state.runtime);
  }
  function showNotice(message) {
    const notice = $("stream-notice"); notice.hidden = false; notice.textContent = message;
  }
  function openEvents() {
    const stream = new EventSource("/events");
    stream.addEventListener("ready", async () => {
      try { await resync(); await refreshRuntime(); }
      catch (error) { showNotice(error.message); }
    });
    stream.addEventListener("result", async (event) => {
      try {
        const notification = JSON.parse(event.data);
        const result = await request(`/results/${encodeURIComponent(notification.result_id)}`);
        absorb([result], true);
        state.syncCursor = notification.cursor;
        await loadAlerts();
      } catch (error) { showNotice(error.message); }
    });
    stream.addEventListener("stream_gap", async () => {
      showNotice("Live notification gap observed. Resynchronizing from durable SQLite results…");
      try { await resync(); showNotice("Durable resynchronization complete."); setTimeout(() => { $("stream-notice").hidden = true; }, 2500); }
      catch (error) { showNotice(error.message); }
    });
    stream.onerror = () => showNotice("Live stream reconnecting; durable results remain available.");
  }
  async function boot() {
    try {
      const [runtime, health] = await Promise.all([request("/runtime"), request("/health")]);
      state.runtime = runtime;
      state.replay = runtime.replay;
      setRuntimeBadge(runtime.state, health.status === "ok");
      $("alert-policy-state").textContent = runtime.alert_policy_version || "Alert projection unavailable";
      renderReplayScenarios(runtime);
      await initialLoad();
      await loadAlerts();
      renderSystem(runtime);
      renderReplayStatus(runtime.replay);
      renderAll();
      if (runtime.dga_model_readiness !== "VERIFIED_READY") {
        const modelCard = [...document.querySelectorAll(".system-card")].find((card) => card.querySelector(".metric-label")?.textContent === "DGA model");
        if (modelCard) modelCard.title = runtime.dga_model_failure_reason || "The exact DGA model artifact is unavailable.";
      }
      openEvents();
    } catch (error) {
      setRuntimeBadge("OFFLINE", false);
      showNotice(error.message || "Runtime could not be reached.");
      $("last-updated").textContent = "Runtime unavailable";
    }
  }
  ["alert-search", "alert-class-filter", "alert-basis-filter", "alert-quality-filter", "alert-visibility-filter"].forEach((id) => $(id).addEventListener("input", renderAlerts));
  ["result-search", "result-family-filter", "result-type-filter"].forEach((id) => $(id).addEventListener("input", renderResults));
  $("load-more").addEventListener("click", () => loadOlder().catch((error) => showNotice(error.message)));
  boot();
})();
