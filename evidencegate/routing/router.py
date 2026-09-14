from typing import Sequence, Dict, Tuple
from evidencegate.domain.events import NetworkObservation
from evidencegate.domain.enums import ObservationType
from evidencegate.registry.plugin import AnalyticPlugin

class LaneTarget(str):
    pass

class RelevanceRouter:
    """
    At registration, compile ObservationType -> candidate lanes. 
    For an observation, invoke only each candidate's pure, bounded route() predicate.
    """
    def __init__(self, plugins: Dict[LaneTarget, AnalyticPlugin]):
        self._plugins = plugins
        self._type_index: Dict[ObservationType, list[LaneTarget]] = {
            obs_type: [] for obs_type in ObservationType
        }
        self._build_index()

    def _build_index(self):
        for lane_target, plugin in self._plugins.items():
            manifest = plugin.manifest()
            for obs_type in manifest.accepted_observation_types:
                self._type_index[obs_type].append(lane_target)

    def route(self, observation: NetworkObservation) -> Tuple[LaneTarget, ...]:
        candidates = self._type_index.get(observation.observation_type, [])
        relevant_lanes = []
        for lane_target in candidates:
            plugin = self._plugins[lane_target]
            if plugin.route(observation):
                relevant_lanes.append(lane_target)
        
        return tuple(relevant_lanes)
