from typing import Any, Optional
from evidencegate.registry.plugin import StateKey

class StateStore:
    """
    Logically owned by the plugin, but operationally owned by runtime.
    Manages bounded state, TTL eviction, gap behavior.
    """
    def __init__(self):
        self._state: dict[StateKey, Any] = {}
        
    def get(self, key: StateKey) -> Optional[Any]:
        return self._state.get(key)
        
    def put(self, key: StateKey, value: Any) -> None:
        self._state[key] = value
        
    def remove(self, key: StateKey) -> None:
        self._state.pop(key, None)
