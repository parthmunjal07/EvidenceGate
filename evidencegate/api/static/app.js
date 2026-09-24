(() => {
  "use strict";

  const state = {
    results: new Map(),
    family: "",
    resultType: "",
    olderCursor: null,
    syncCursor: null,
    runtime: null,
    alerts: [],
    statusItems: [],
  };

  const el = (id) => document.getElementById(id);
  const pretty = (value) => JSON.stringify(value, null, 2);
  const statusText = (value) => value.replaceAll("_", " ").toLowerCase();

  async function request(url, options) {
    const response = await fetch(url, options);
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
    return body;
  }

  function shortEvidence(evidence) {
    if (evidence && evidence.evidence_kind === "DGA_LEXICAL_MODEL_EVIDENCE") {
      const score = evidence.dga_labelled_lexical_resemblance_score;
      return score === undefined
        ? "DGA lexical model evidence unavailable"
        : `DGA lexical model evidence · DGA-labelled lexical resemblance score: ${score}`;
    }
    const entries = Object.entries(evidence || {}).slice(0, 3);
    if (!entries.length) return "No structured evidence fields";
    return entries.map(([key, value]) => `${key}: ${typeof value === "object" ? "…" : value}`).join(" · ");
  }

  function visibleResults() {
    return [...state.results.values()]
      .filter((item) => !state.family || item.family === state.family)
      .filter((item) => !state.resultType || item.result_type === state.resultType)
      .sort((a, b) => b.created_time.localeCompare(a.created_time) || b.result_id.localeCompare(a.result_id));
  }

  function renderSummary(results) {
    el("result-count").textContent = String(results.length);
    el("quality-count").textContent = String(results.filter((item) => item.status_snapshot.quality_degraded || item.result_type === "QUALITY_DEGRADED").length);
    el("insufficient-count").textContent = String(results.filter((item) => item.result_type === "INSUFFICIENT_EVIDENCE").length);
  }

  function renderTimeline() {
    const results = visibleResults();
    renderSummary(results);
    const timeline = el("timeline");
    timeline.replaceChildren();
    if (!results.length) {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "No durable results match this view.";
      timeline.append(empty);
      return;
    }
    for (const result of results) {
      const card = el("result-template").content.firstElementChild.cloneNode(true);
      card.querySelector("time").textContent = new Date(result.created_time).toLocaleTimeString();
      card.querySelector(".family").textContent = result.family;
      card.querySelector(".mechanism").textContent = result.mechanism_id || result.lane_id;
      card.querySelector(".result-type").textContent = statusText(result.result_type);
      card.querySelector(".entity").textContent = result.entity_reference;
      card.querySelector(".evidence-summary").textContent = shortEvidence(result.evidence);
      const quality = card.querySelector(".quality-badge");
      quality.textContent = result.status_snapshot.quality_degraded ? "quality degraded" : "quality stated";
      quality.classList.toggle("degraded", result.status_snapshot.quality_degraded);
      card.querySelector(".visibility-badge").textContent = `${result.visibility_snapshot.available.length} visible`;
      card.querySelector('[data-field="observed"]').textContent = pretty({
        entity_reference: result.entity_reference,
        source_observation_ids: result.source_observation_ids,
        evidence_interval: result.evidence_interval,
      });
      card.querySelector('[data-field="evidence"]').textContent = pretty(result.evidence);
      card.querySelector('[data-field="missing"]').textContent = pretty(result.missing_prerequisites);
      card.querySelector('[data-field="visibility"]').textContent = pretty(result.visibility_snapshot);
      card.querySelector('[data-field="quality"]').textContent = pretty(result.quality_snapshot);
      card.querySelector('[data-field="claim"]').textContent = result.claim_ceiling;
      card.querySelector('[data-field="provenance"]').textContent = pretty({
        result_id: result.result_id,
        source_ids: result.source_ids,
        provenance_refs: result.provenance_refs,
        parser_refs: result.parser_refs,
        model_refs: result.model_refs,
        governing_ids: result.governing_ids,
        config_hash: result.config_hash,
        state_version: result.state_version,
      });
      timeline.append(card);
    }
  }

  function renderAlerts() {
    const host = el("alert-timeline");
    host.replaceChildren();
    if (!state.alerts.length) {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "No review findings in the current analyst queue.";
      host.append(empty);
    }
    for (const alert of state.alerts) {
      const card = el("alert-template").content.firstElementChild.cloneNode(true);
      card.querySelector("time").textContent = new Date(alert.timestamp).toLocaleTimeString();
      card.querySelector(".alert-class").textContent = alert.threat_class;
      card.querySelector(".alert-severity").textContent = `${alert.severity} · analyst priority`;
      card.querySelector(".alert-evidence").textContent = shortEvidence(alert.supporting_evidence.structured);
      card.querySelector('[data-field="mechanism"]').textContent = alert.mechanism_id;
      card.querySelector('[data-field="confidence"]').textContent = alert.confidence_score === null
        ? `${alert.confidence_basis}: ${alert.confidence_statement}. Numeric attack probability: not defined by this analytic.`
        : `DGA-labelled lexical resemblance score: ${alert.confidence_score}. Basis: ${alert.confidence_basis}. ${alert.confidence_statement}.`;
      card.querySelector('[data-field="evidence"]').textContent = pretty(alert.supporting_evidence);
      card.querySelector('[data-field="quality"]').textContent = pretty(alert.quality);
      card.querySelector('[data-field="visibility"]').textContent = pretty(alert.visibility);
      card.querySelector('[data-field="claim"]').textContent = alert.claim_ceiling;
      const source = card.querySelector('[data-field="source"]');
      for (const id of alert.source_result_ids) {
        const link = document.createElement("a");
        link.href = `/results/${encodeURIComponent(id)}`;
        link.textContent = id;
        source.append(link);
      }
      host.append(card);
    }
    const statuses = el("status-timeline");
    statuses.replaceChildren();
    for (const item of state.statusItems) {
      const card = document.createElement("article");
      card.className = "status-card";
      const title = document.createElement("strong");
      title.textContent = `${item.priority} · ${item.status_kind} · ${item.mechanism_id}`;
      const details = document.createElement("pre");
      details.textContent = pretty({
        result_type: item.result_type,
        supporting_evidence: item.supporting_evidence,
        missing_prerequisites: item.missing_prerequisites,
        visibility: item.visibility,
        quality: item.quality,
        claim_ceiling: item.claim_ceiling,
        governing_ids: item.governing_ids,
        provenance_refs: item.provenance_refs,
      });
      card.append(title, details);
      for (const id of item.source_result_ids) {
        const link = document.createElement("a");
        link.href = `/results/${encodeURIComponent(id)}`;
        link.textContent = `Source result ${id}`;
        card.append(link);
      }
      statuses.append(card);
    }
    if (!state.statusItems.length) {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "No system or quality status records.";
      statuses.append(empty);
    }
  }

  async function loadAlerts() {
    if (!state.runtime?.alert_projection_available) return;
    const response = await request("/alerts?limit=500");
    state.alerts = response.alerts;
    state.statusItems = response.status_items;
    el("alert-count").textContent = String(state.alerts.length);
    el("status-count").textContent = String(state.statusItems.length);
    renderAlerts();
  }

  function selectView(name) {
    const alerts = name === "alerts";
    el("results-panel").hidden = alerts;
    el("alerts-panel").hidden = !alerts;
    el("results-view").classList.toggle("active", !alerts);
    el("alerts-view").classList.toggle("active", alerts);
  }

  function renderFamilies(runtime) {
    const host = el("family-filters");
    host.replaceChildren();
    for (const item of runtime.family_status) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "family-button";
      button.dataset.family = item.family;
      const name = document.createElement("span");
      name.textContent = item.family;
      const detail = document.createElement("small");
      detail.textContent = item.status;
      button.append(name, detail);
      button.addEventListener("click", () => {
        state.family = state.family === item.family ? "" : item.family;
        document.querySelectorAll(".family-button").forEach((node) => node.classList.toggle("active", node.dataset.family === state.family));
        renderTimeline();
      });
      host.append(button);
    }
  }

  function renderReplayControls(runtime) {
    const host = el("replay-controls");
    host.replaceChildren();
    for (const scenario of runtime.scenarios) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = `Run ${scenario.label}`;
      button.addEventListener("click", async () => {
        setReplayDisabled(true);
        try {
          await request("/replay", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ scenario: scenario.id, speed: 0 }),
          });
          await monitorReplay();
        } catch (error) {
          el("replay-status").textContent = error.message;
          setReplayDisabled(false);
        }
      });
      host.append(button);
    }
  }

  function setReplayDisabled(value) {
    document.querySelectorAll("#replay-controls button").forEach((button) => { button.disabled = value; });
  }

  async function monitorReplay() {
    const replay = await request("/replay/status");
    el("replay-status").textContent = `${replay.state} · ${replay.source_type || "no source"} · ${replay.scenario || "no scenario"} · ${replay.records_read} read · ${replay.observations_emitted} observations · ${replay.results_persisted} results persisted`;
    el("runtime-state").textContent = replay.state === "RUNNING" ? "REPLAYING" : "ONLINE";
    if (replay.state === "RUNNING") {
      setTimeout(monitorReplay, 250);
    } else {
      setReplayDisabled(false);
      await resync();
    }
  }

  function absorb(results) {
    for (const result of results) state.results.set(result.result_id, result);
    renderTimeline();
  }

  async function initialLoad() {
    const page = await request("/results?limit=100");
    absorb(page.results);
    state.olderCursor = page.next_cursor;
    state.syncCursor = page.sync_cursor;
    el("load-more").hidden = !state.olderCursor;
  }

  async function loadOlder() {
    if (!state.olderCursor) return;
    const page = await request(`/results?limit=100&cursor=${encodeURIComponent(state.olderCursor)}`);
    absorb(page.results);
    state.olderCursor = page.next_cursor;
    el("load-more").hidden = !state.olderCursor;
  }

  async function resync() {
    if (!state.syncCursor) {
      await initialLoad();
      return;
    }
    let cursor = state.syncCursor;
    while (true) {
      const page = await request(`/results?limit=500&cursor=${encodeURIComponent(cursor)}`);
      absorb(page.results);
      if (page.sync_cursor) state.syncCursor = page.sync_cursor;
      if (page.results.length < 500) break;
      cursor = page.next_cursor;
    }
    await loadAlerts();
  }

  function openEvents() {
    const stream = new EventSource("/events");
    stream.addEventListener("ready", () => resync().catch(showStreamError));
    stream.addEventListener("result", async (event) => {
      const notification = JSON.parse(event.data);
      try {
        const result = await request(`/results/${encodeURIComponent(notification.result_id)}`);
        absorb([result]);
        state.syncCursor = notification.cursor;
      } catch (error) {
        showStreamError(error);
      }
    });
    stream.addEventListener("stream_gap", async () => {
      const notice = el("stream-notice");
      notice.hidden = false;
      notice.textContent = "Live notification gap observed. Resynchronizing from durable SQLite…";
      try {
        await resync();
        notice.textContent = "Durable resynchronization complete.";
        setTimeout(() => { notice.hidden = true; }, 2500);
      } catch (error) {
        showStreamError(error);
      }
    });
    stream.onerror = () => {
      const notice = el("stream-notice");
      notice.hidden = false;
      notice.textContent = "Live stream reconnecting; durable results remain available.";
    };
  }

  function showStreamError(error) {
    const notice = el("stream-notice");
    notice.hidden = false;
    notice.textContent = error.message;
  }

  async function boot() {
    try {
      const runtime = await request("/runtime");
      state.runtime = runtime;
      el("runtime-state").textContent = runtime.state;
      el("runtime-dot").style.background = "var(--mint)";
      el("active-count").textContent = String(runtime.targets.filter((item) => item.implementation !== "REGISTERED_SHELL").length);
      el("dga-status").textContent = runtime.dga_model_readiness === "VERIFIED_READY"
        ? "DGA — ACTIVE LEXICAL MODEL EVIDENCE"
        : "DGA — ACTIVE LANE — MODEL UNAVAILABLE";
      el("dga-readiness").textContent = runtime.dga_model_readiness === "VERIFIED_READY"
        ? "Verified DGA-A1/M1-R1 lexical review evidence; no maliciousness threshold."
        : `${runtime.dga_model_readiness}: ${runtime.dga_model_failure_reason || "exact model unavailable"}`;
      renderFamilies(runtime);
      renderReplayControls(runtime);
      await initialLoad();
      el("alerts-view").disabled = !runtime.alert_projection_available;
      if (runtime.alert_projection_available) {
        el("alert-policy-label").textContent = `${runtime.alert_policy_version} · ACTIVE`;
        await loadAlerts();
      } else {
        el("alert-policy-label").textContent = "Alert projection disabled for development";
      }
      await monitorReplay();
      openEvents();
    } catch (error) {
      el("runtime-state").textContent = "OFFLINE";
      showStreamError(error);
    }
  }

  el("all-families").addEventListener("click", () => {
    state.family = "";
    document.querySelectorAll(".family-button").forEach((node) => node.classList.remove("active"));
    renderTimeline();
  });
  el("type-filter").addEventListener("change", (event) => {
    state.resultType = event.target.value;
    renderTimeline();
  });
  el("load-more").addEventListener("click", loadOlder);
  el("results-view").addEventListener("click", () => selectView("results"));
  el("alerts-view").addEventListener("click", () => selectView("alerts"));
  boot();
})();
