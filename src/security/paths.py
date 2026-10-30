from pathlib import Path

from state.errors import ErrorCode, StudioError
from state.io import native_path


class PathPolicy:
    def __init__(self, read_roots, write_roots, immutable_roots=()):
        self.read_roots = tuple(native_path(Path(p)) for p in read_roots)
        self.write_roots = tuple(native_path(Path(p)) for p in write_roots)
        self.immutable_roots = tuple(native_path(Path(p)) for p in immutable_roots)

    @staticmethod
    def _inside(path, roots):
        return any(path == root or path.is_relative_to(root) for root in roots)

    def check(self, path: Path, *, write=False) -> Path:
        path = native_path(path)
        if not self._inside(path, self.write_roots if write else self.read_roots):
            raise StudioError(ErrorCode.SECURITY_BLOCK, "Path outside authorized roots")
        if write and self._inside(path, self.immutable_roots):
            raise StudioError(ErrorCode.SECURITY_BLOCK, "Original packages and project inputs are immutable")
        if any(":" in part for part in path.parts[1:]):
            raise StudioError(ErrorCode.SECURITY_BLOCK, "Alternate data stream is forbidden")
        return path
