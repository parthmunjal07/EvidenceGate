from dataclasses import dataclass
from typing import Dict, Tuple
from evidencegate.domain.events import NetworkObservation
from evidencegate.domain.enums import CapabilityState, ObservationType, RouteReason
from evidencegate.registry.manifest import PluginManifest
from evidencegate.registry.plugin import AnalyticPlugin

class LaneTarget(str):
    pass


@dataclass(frozen=True, slots=True)
class RouteDecision:
    """The independent, explainable compatibility result for one lane."""
    target: LaneTarget
    selected: bool
    reasons: tuple[RouteReason, ...]
    predicate_exception_type: str | None = None
    predicate_error: str | None = None


@dataclass(frozen=True, slots=True)
class RoutingPlan:
    """In-memory, deterministic routing result for one observation."""
    observation_id: str
    selected_targets: tuple[LaneTarget, ...]
    decisions: tuple[RouteDecision, ...]

class RelevanceRouter:
    """
    At registration, compile ObservationType -> candidate lanes. 
    For an observation, invoke only each candidate's pure, bounded route() predicate.
    """
    def __init__(self, plugins: Dict[LaneTarget, AnalyticPlugin]):
        self._plugins = dict(plugins)
        self._manifests: Dict[LaneTarget, PluginManifest] = {}
        self._type_index: Dict[ObservationType, list[LaneTarget]] = {
            obs_type: [] for obs_type in ObservationType
        }
        self._build_index()

    def _build_index(self):
        plugin_ids: set[str] = set()
        for lane_target, plugin in self._plugins.items():
            manifest = plugin.manifest()
            if manifest.plugin_id in plugin_ids:
                raise ValueError(f"duplicate plugin_id registered: {manifest.plugin_id}")
            plugin_ids.add(manifest.plugin_id)
            self._manifests[lane_target] = manifest
            for obs_type in manifest.accepted_observation_types:
                self._type_index[obs_type].append(lane_target)

    def plan(self, observation: NetworkObservation) -> RoutingPlan:
        candidates = self._type_index.get(observation.observation_type, ())
        selected_targets: list[LaneTarget] = []
        decisions: list[RouteDecision] = []
        for lane_target in candidates:
            plugin = self._plugins[lane_target]
            manifest = self._manifests[lane_target]
            reasons = self._structural_reasons(observation, manifest)
            if reasons:
                decisions.append(RouteDecision(lane_target, False, tuple(reasons)))
                continue
            try:
                if plugin.route(observation):
                    selected_targets.append(lane_target)
                    decisions.append(RouteDecision(lane_target, True, (RouteReason.SELECTED,)))
                else:
                    decisions.append(RouteDecision(lane_target, False, (RouteReason.PREDICATE_FALSE,)))
            except Exception as exc:
                decisions.append(RouteDecision(
                    lane_target, False, (RouteReason.PREDICATE_ERROR,),
                    type(exc).__name__, str(exc)[:500],
                ))
        return RoutingPlan(observation.observation_id, tuple(selected_targets), tuple(decisions))

    @staticmethod
    def _structural_reasons(
        observation: NetworkObservation, manifest: PluginManifest
    ) -> list[RouteReason]:
        reasons: list[RouteReason] = []
        contracts = manifest.required_observation_contracts
        placeholders = {"NOT_YET_GOVERNED", "NOT_APPLICABLE"}
        if contracts and not all(contract in placeholders for contract in contracts):
            if observation.observation_contract not in contracts:
                reasons.append(RouteReason.CONTRACT_MISMATCH)
        if any(field not in observation.present_fields for field in manifest.required_fields):
            reasons.append(RouteReason.REQUIRED_FIELD_MISSING)
        if any(
            observation.visibility.state(capability) is not CapabilityState.AVAILABLE
            for capability in manifest.required_visibility_capabilities
        ):
            reasons.append(RouteReason.REQUIRED_CAPABILITY_UNAVAILABLE)
        if manifest.allowed_finality and observation.finality not in manifest.allowed_finality:
            reasons.append(RouteReason.FINALITY_UNSUPPORTED)
        if (manifest.allowed_availability_basis
                and observation.availability_basis not in manifest.allowed_availability_basis):
            reasons.append(RouteReason.AVAILABILITY_UNSUPPORTED)
        return reasons

    def route(self, observation: NetworkObservation) -> Tuple[LaneTarget, ...]:
        """Backward-compatible selected-target convenience wrapper."""
        return self.plan(observation).selected_targets

    def plugin_id_for(self, target: LaneTarget) -> str:
        """Return registration-time plugin identity for bounded diagnostics."""
        return self._manifests[target].plugin_id
