"""Neutral identities shared by plugin and runtime state contracts."""

from enum import Enum


class StateKey(str):
    pass


class StateOperation(str, Enum):
    NO_CHANGE = "NO_CHANGE"
    UPSERT = "UPSERT"
    DELETE = "DELETE"
    RESET = "RESET"
    REENTER_WARMUP = "REENTER_WARMUP"
