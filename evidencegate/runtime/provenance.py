"""Factual runtime-owned provenance extraction for result finalization."""

from evidencegate.domain.events import NetworkObservation


def parser_refs_from_observation(observation: NetworkObservation) -> tuple[str, ...]:
    """Return declared parser provenance without inferring unavailable fields."""
    if "parser_version" not in getattr(observation, "present_fields", frozenset()):
        return ()
    parser_version = getattr(getattr(observation, "typed_payload", None), "parser_version", None)
    if not isinstance(parser_version, str) or not parser_version.strip():
        return ()
    observation_type = getattr(observation, "observation_type", None)
    type_name = getattr(observation_type, "value", None)
    return (f"{type_name}:{parser_version}",) if type_name else ()
