"""M5-01: immutable, runtime-owned result finalization."""
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import asyncio
import pytest

from evidencegate.domain.enums import (
    AnalyticUnavailableReason,
    EvidenceReadiness,
    GapAction,
    ResultType,
    ScientificStatus,
)
from evidencegate.domain.governance import LaneGovernance
from evidencegate.plugins.scaffolds.basic_scaffold import BasicScaffoldPlugin
from evidencegate.registry.plugin import PluginProcessOutcome, StateKey
from evidencegate.results.finalizer import ResultEmissionContext, ResultFinalizer
from evidencegate.results.types import (
    AnalyticUnavailable,
    CorrelationFinding,
    InsufficientEvidence,
    PluginStatus,
    PrerequisiteMissing,
    QualityDegraded,
    ResultDraft,
    ReviewFinding,
    ThreatAlert,
)
from evidencegate.runtime.shard import LaneShard
from evidencegate.runtime.state import StateStore


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def manifest(*, analytic_version: str = "analytic-1"):
    return replace(
        BasicScaffoldPlugin().manifest(),
        plugin_id="m5-plugin",
        plugin_version="plugin-1",
        analytic_version=analytic_version,
        taxonomy=("network", "test", "m5"),
        governing_claim_ids=("claim-1", "claim-1"),
        governing_decision_ids=("decision-1",),
        allowed_result_types=tuple(ResultType),
    )


def governance(*, version: str = "gov-1", allowed=tuple(ResultType)):
    return LaneGovernance(
        analytic_lane="m5-lane",
        scientific_status=ScientificStatus.MODEL_VALIDATED,
        scientific_phase="test",
        scientific_blockers=(),
        claim_ceiling="REVIEW_ONLY",
        governance_version=version,
        effective_at=NOW,
        allowed_result_types=allowed,
        ingest_permitted=True,
    )


def context(*, trigger: str | None = "obs-1", refs=("quality-1",), provenance=("prov-1",)):
    return ResultEmissionContext(
        lane_id="m5-lane",
        causal_result_time=NOW,
        quality_refs=refs,
        provenance_refs=provenance,
        readiness=EvidenceReadiness.READY,
        quality_degraded=False,
        trigger_reference=trigger,
    )


def draft(kind=ResultType.REVIEW_FINDING, **changes):
    values = dict(
        result_type=kind,
        entity_reference="entity-1",
        evidence_items=("evidence-1",),
        missing_prerequisites=("field-x",),
    )
    values.update(changes)
    return ResultDraft(**values)


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (ResultType.THREAT_ALERT, ThreatAlert),
        (ResultType.REVIEW_FINDING, ReviewFinding),
        (ResultType.ANALYTIC_UNAVAILABLE, AnalyticUnavailable),
        (ResultType.PREREQUISITE_MISSING, PrerequisiteMissing),
        (ResultType.INSUFFICIENT_EVIDENCE, InsufficientEvidence),
        (ResultType.QUALITY_DEGRADED, QualityDegraded),
        (ResultType.PLUGIN_STATUS, PluginStatus),
        (ResultType.CORRELATION_FINDING, CorrelationFinding),
    ],
)
def test_draft_promotes_to_exact_final_subtype(kind, expected):
    changes = {}
    if kind is ResultType.THREAT_ALERT:
        changes["confidence"] = "DEFINED"
    if kind is ResultType.ANALYTIC_UNAVAILABLE:
        changes["reason_code"] = AnalyticUnavailableReason.SCIENTIFIC_NOT_READY
    if kind is ResultType.CORRELATION_FINDING:
        changes["linked_result_ids"] = ("result:a", "result:a", "result:b")
    result = ResultFinalizer.finalize(draft(kind, **changes), manifest(), governance(), context())
    assert type(result) is expected
    if isinstance(result, CorrelationFinding):
        assert result.linked_result_ids == ("result:a", "result:b")


def test_runtime_owns_metadata_and_references() -> None:
    result = ResultFinalizer.finalize(
        draft(evidence_items=("evidence-1", "obs-1", "evidence-1")),
        manifest(), governance(),
        context(refs=("quality-1", "quality-2", "quality-1"), provenance=("prov-1", "prov-2", "prov-1")),
    )
    assert result.schema_version == "2.0"
    assert (result.lane_id, result.plugin_id, result.plugin_version, result.analytic_version) == (
        "m5-lane", "m5-plugin", "plugin-1", "analytic-1"
    )
    assert result.taxonomy == ("network", "test", "m5")
    assert result.governing_ids == ("claim-1", "decision-1")
    assert result.claim_ceiling == "REVIEW_ONLY"
    assert result.evidence_items == ("evidence-1", "obs-1")
    assert result.quality_refs == ("quality-1", "quality-2")
    assert result.provenance_refs == ("prov-1", "prov-2")
    assert result.status_snapshot.governance_version == "gov-1"
    with pytest.raises(FrozenInstanceError):
        result.status_snapshot.quality_degraded = True  # type: ignore[misc]
    with pytest.raises(TypeError, match="plugin_id"):
        ResultDraft(
            ResultType.REVIEW_FINDING, "entity-1", (), (), plugin_id="forged"  # type: ignore[call-arg]
        )


def test_identity_is_deterministic_and_tracks_scientific_versions_and_evidence() -> None:
    baseline = ResultFinalizer.finalize(draft(), manifest(), governance(), context())
    assert baseline == ResultFinalizer.finalize(draft(), manifest(), governance(), context())
    assert baseline.result_id != ResultFinalizer.finalize(
        draft(evidence_items=("other-evidence",)), manifest(), governance(), context()
    ).result_id
    assert baseline.result_id != ResultFinalizer.finalize(
        draft(), manifest(analytic_version="analytic-2"), governance(), context()
    ).result_id
    assert baseline.result_id != ResultFinalizer.finalize(
        draft(), manifest(), governance(version="gov-2"), context()
    ).result_id


def test_validator_rules_remain_authoritative() -> None:
    with pytest.raises(ValueError, match="confidence/severity"):
        ResultFinalizer.finalize(draft(confidence="forbidden"), manifest(), governance(), context())
    with pytest.raises(ValueError, match="confidence semantics"):
        ResultFinalizer.finalize(
            draft(ResultType.THREAT_ALERT), manifest(), governance(), context()
        )
    with pytest.raises(ValueError, match="not allowed by governance"):
        ResultFinalizer.finalize(
            draft(ResultType.THREAT_ALERT, confidence="DEFINED"), manifest(),
            governance(allowed=(ResultType.REVIEW_FINDING,)), context(),
        )


@pytest.mark.asyncio
async def test_shard_finalizes_normal_and_lifecycle_results_and_suppresses_abstention() -> None:
    class LifecyclePlugin(BasicScaffoldPlugin):
        def manifest(self):
            return replace(super().manifest(), plugin_id="m5-plugin", taxonomy=("network", "test", "m5"))

        async def process(self, observation, context, state):
            return PluginProcessOutcome((draft(),))

        def state_key(self, observation):
            return None

        async def on_watermark(self, watermark, context):
            return PluginProcessOutcome((draft(entity_reference="watermark"),))

    plugin = LifecyclePlugin()
    emitted = []
    finalizer = lambda value, ctx: ResultFinalizer.finalize(value, manifest(), governance(), ctx)
    shard = LaneShard(0, plugin, StateStore(), lambda result: collect(emitted, result),
                       lane_id="m5-lane", result_finalizer=finalizer)

    # A direct lifecycle callback uses the same finalizer and causal watermark.
    await shard.handle_watermark(NOW + timedelta(seconds=5), 0, publish_results=True)
    assert isinstance(emitted[-1], ReviewFinding)
    assert emitted[-1].created_time == NOW + timedelta(seconds=5)
    assert emitted[-1].evidence_items[-1].startswith("watermark:")

    # Normal observation processing supplies causal time, observation evidence,
    # quality, and provenance to the same finalizer path.
    shard.start()
    observation = SimpleNamespace(
        observation_id="normal-observation",
        event_time=NOW,
        causal_available_time=NOW + timedelta(seconds=2),
        quality_ref="normal-quality",
        provenance_ref="normal-provenance",
        source_id="source",
    )
    await shard.put(observation)
    await asyncio.wait_for(shard.queue.join(), timeout=1)
    await shard.stop()
    assert emitted[-1].created_time == NOW + timedelta(seconds=2)
    assert emitted[-1].evidence_items[-1] == "normal-observation"
    assert emitted[-1].quality_refs == ("normal-quality",)
    assert emitted[-1].provenance_refs == ("normal-provenance",)

    # An abstaining key suppresses publication before finalization/delivery.
    before = len(emitted)
    shard.apply_gap_action(GapAction.ABSTAIN_UNTIL_RECOVERED, "gap-1", StateKey("key"), NOW)
    outcome = PluginProcessOutcome((draft(),))
    await shard._deliver_lifecycle_outcome(outcome, NOW, "on_expire", StateKey("key"), True)
    assert len(emitted) == before


async def collect(target, value):
    target.append(value)
