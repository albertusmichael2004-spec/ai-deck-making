from dataclasses import dataclass
from typing import Callable, Protocol, runtime_checkable

from state.errors import ErrorCode, StudioError


@runtime_checkable
class ProjectContract(Protocol):
    def snapshot(self) -> str: ...
    def begin(self) -> str: ...
    def commit(self, transaction_id: str, validator: Callable) -> dict: ...
    def rollback(self, snapshot_id: str, expected: dict) -> dict: ...
    def detect_conflict(self, expected: dict) -> bool: ...


@runtime_checkable
class FilesContract(Protocol):
    def inspect(self, path, role: str) -> dict: ...
    def materialize(self, source, destination, role: str) -> dict: ...


@dataclass(frozen=True)
class Capability:
    name: str
    available: bool
    version: str
    reason: str | None = None


class CapabilityRegistry:
    def __init__(self):
        self._entries = {}

    def register(self, capability: Capability, operation: Callable | None = None):
        if capability.name in self._entries:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Capability already registered")
        if capability.available and operation is None:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Available capability needs an implementation")
        self._entries[capability.name] = (capability, operation)

    def invoke(self, name, *args, **kwargs):
        entry = self._entries.get(name)
        if entry is None or not entry[0].available:
            raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE, "Capability unavailable", capability=name, reason=entry[0].reason if entry else "not_registered")
        return entry[1](*args, **kwargs)

    def manifest(self):
        from dataclasses import asdict
        return [asdict(entry[0]) for entry in self._entries.values()]
