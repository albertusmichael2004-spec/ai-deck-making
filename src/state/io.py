import hashlib
import json
import os
import tempfile
import time
import shutil
from pathlib import Path

import yaml


def native_path(path: Path) -> Path:
    """Windows extended paths avoid the canonical library exceeding MAX_PATH."""
    resolved = Path(path).resolve()
    if os.name == "nt" and not str(resolved).startswith("\\\\?\\"):
        value = str(resolved)
        return Path("\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value)
    return resolved


def logical_path(path: Path) -> Path:
    """COM/export APIs reject extended path syntax; keep durable identities normal."""
    value = str(path)
    if value.startswith("\\\\?\\UNC\\"):
        return Path("\\\\" + value[8:])
    if value.startswith("\\\\?\\"):
        return Path(value[4:])
    return Path(value)


def open_read(path: Path):
    """Read with compatible Office sharing flags; never unlock or write a file."""
    path=native_path(path)
    try:return path.open("rb")
    except PermissionError:
        if os.name!="nt":raise
        import win32file,win32con,msvcrt
        handle=win32file.CreateFile(str(path),win32con.GENERIC_READ,win32con.FILE_SHARE_READ|win32con.FILE_SHARE_WRITE|win32con.FILE_SHARE_DELETE,None,win32con.OPEN_EXISTING,win32con.FILE_ATTRIBUTE_NORMAL,None)
        raw=handle.Detach()
        try:descriptor=msvcrt.open_osfhandle(raw,os.O_RDONLY|os.O_BINARY)
        except Exception:
            win32file.CloseHandle(raw);raise
        return os.fdopen(descriptor,"rb")


def copy_file(source: Path,destination: Path):
    with open_read(source) as incoming,native_path(destination).open("wb") as outgoing:
        shutil.copyfileobj(incoming,outgoing,1024*1024)
    shutil.copystat(native_path(source),native_path(destination))


def sha256(path: Path) -> str:
    with open_read(path) as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fingerprint(path: Path) -> dict:
    path = native_path(path)
    if not path.exists():
        return {"exists": False, "sha256": None, "mtime_ns": None, "bytes": None}
    stat = path.stat()
    return {"exists": True, "sha256": sha256(path), "mtime_ns": stat.st_mtime_ns, "bytes": stat.st_size}


def atomic_bytes(path: Path, data: bytes):
    path = native_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".studio-tmp-", dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        replace_file(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def replace_file(source: Path, destination: Path):
    """Bounded retries for transient Windows sharing locks, with no delete fallback."""
    for attempt in range(5):
        try:
            os.replace(source, destination)
            return
        except PermissionError as exc:
            if os.name != "nt" or getattr(exc, "winerror", None) not in {5, 32, 33} or attempt == 4:
                raise
            time.sleep(0.02 * (2 ** attempt))


def write_json(path: Path, value):
    atomic_bytes(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))


def read_json(path: Path):
    return json.loads(native_path(path).read_text(encoding="utf-8"))


def write_yaml(path: Path, value):
    atomic_bytes(path, yaml.safe_dump(value, sort_keys=False, allow_unicode=True).encode("utf-8"))


def read_yaml(path: Path):
    return yaml.safe_load(native_path(path).read_text(encoding="utf-8"))
