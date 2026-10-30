"""Read an Office-owned file with Windows sharing flags; never break its lock."""
import hashlib
from pathlib import Path

from state.errors import StudioError,ErrorCode
from state.io import fingerprint,native_path,logical_path


def disk_fingerprint(path):
    path=native_path(Path(path))
    try:return fingerprint(path)
    except PermissionError:
        import win32file
        import win32con
        before=path.stat();handle=None;digest=hashlib.sha256()
        try:
            handle=win32file.CreateFile(str(logical_path(path)),win32con.GENERIC_READ,win32con.FILE_SHARE_READ|win32con.FILE_SHARE_WRITE|win32con.FILE_SHARE_DELETE,None,win32con.OPEN_EXISTING,win32con.FILE_ATTRIBUTE_NORMAL,None)
            while True:
                _,data=win32file.ReadFile(handle,1024*1024)
                if not data:break
                digest.update(data)
        except Exception as exc:raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE,"Office file cannot be read safely with shared access; save-existing is unavailable until a verified disk fingerprint can be obtained") from exc
        finally:
            if handle is not None:handle.Close()
        after=path.stat()
        if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise StudioError(ErrorCode.LIVE_PRESENTATION_CONFLICT,"Disk file changed during shared fingerprinting")
        return {"exists":True,"sha256":digest.hexdigest(),"mtime_ns":after.st_mtime_ns,"bytes":after.st_size}
