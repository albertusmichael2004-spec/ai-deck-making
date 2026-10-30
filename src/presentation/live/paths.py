"""Resolve Office cloud names only through registered Windows sync mappings."""
from pathlib import Path,PurePosixPath
from urllib.parse import urlsplit,unquote

from state.errors import StudioError,ErrorCode
from state.io import logical_path,native_path


def sync_mounts():
    import winreg
    mounts=[]
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r"Software\SyncEngines\Providers\OneDrive",0,winreg.KEY_READ) as root:
            for index in range(winreg.QueryInfoKey(root)[0]):
                with winreg.OpenKey(root,winreg.EnumKey(root,index),0,winreg.KEY_QUERY_VALUE) as key:
                    try:mounts.append((winreg.QueryValueEx(key,"URLNamespace")[0],winreg.QueryValueEx(key,"MountPoint")[0]))
                    except OSError:continue
    except OSError:pass
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r"Software\Microsoft\OneDrive\Accounts\Personal",0,winreg.KEY_QUERY_VALUE) as key:
            cid=winreg.QueryValueEx(key,"cid")[0];folder=winreg.QueryValueEx(key,"UserFolder")[0]
            import re
            if re.fullmatch(r"[a-fA-F0-9]{16}",cid):mounts.append(("https://d.docs.live.net/"+cid+"/",folder))
    except OSError:pass
    return mounts


def local_identity(value,*,mounts=None):
    text=str(value);parsed=urlsplit(text)
    if parsed.scheme.lower() not in {"https","http"}:return str(logical_path(native_path(Path(value)))).replace("/","\\").casefold()
    if parsed.scheme!="https" or parsed.query or parsed.fragment or parsed.username or parsed.password:raise StudioError(ErrorCode.LIVE_PRESENTATION_CONFLICT,"Unrecognized Office cloud presentation identity")
    choices=sync_mounts() if mounts is None else mounts
    for namespace,mount in sorted(choices,key=lambda row:len(row[0]),reverse=True):
        prefix=urlsplit(namespace);path=unquote(parsed.path);base=unquote(prefix.path).rstrip("/")
        if parsed.netloc.casefold()!=prefix.netloc.casefold() or not path.casefold().startswith(base.casefold()+"/"):continue
        relative=path[len(base):].lstrip("/");parts=PurePosixPath(relative).parts
        if not parts or any(part in {"..","."} or "\\" in part or ":" in part for part in parts):raise StudioError(ErrorCode.SECURITY_BLOCK,"Office cloud identity escaped its registered sync root")
        root=native_path(Path(mount));resolved=native_path(root.joinpath(*parts))
        if not resolved.is_relative_to(root):raise StudioError(ErrorCode.SECURITY_BLOCK,"Cloud target resolved outside its registered sync root")
        return str(logical_path(resolved)).replace("/","\\").casefold()
    raise StudioError(ErrorCode.LIVE_PRESENTATION_CONFLICT,"Office URL has no verified local sync mapping; provide a local working copy")
