from typing import Protocol, AsyncIterator, Any
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class SourceManifest:
    source_id: str
    source_kind: str
    capture_start: Any
    capture_end: Any

@dataclass(frozen=True, slots=True)
class RawSourceRecord:
    raw_data: bytes
    timestamp: Any
    position: str

class InputSource(Protocol):
    source_id: str
    source_kind: str
    
    async def open(self) -> SourceManifest: ...
    
    async def records(self) -> AsyncIterator[RawSourceRecord]: ...
    
    async def pause(self) -> None: ...
    
    async def close(self) -> None: ...
