"""Content-aware slide hashes include every reachable internal dependency."""
import hashlib
import posixpath
from urllib.parse import unquote

from presentation.backends.xml import parse
from state.errors import StudioError,ErrorCode


def slide_fingerprint(package,part):
    seen={};queue=[part]
    while queue:
        name=queue.pop()
        if name in seen:continue
        if name not in package:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Reference dependency is unresolved")
        payload=package[name][1]
        # XML canonicalization ignores incidental attribute ordering, never content.
        if name.endswith((".xml",".rels")):
            from lxml import etree
            payload=etree.tostring(parse(payload),method="c14n")
        seen[name]=hashlib.sha256(payload).hexdigest()
        rel=posixpath.join(posixpath.dirname(name),"_rels",posixpath.basename(name)+".rels")
        if rel not in package:continue
        seen[rel]=hashlib.sha256(package[rel][1]).hexdigest()
        for row in parse(package[rel][1]):
            if row.get("TargetMode")=="External":continue
            target=unquote(row.get("Target",""));target=target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(posixpath.dirname(name),target))
            if target.startswith("../"):raise StudioError(ErrorCode.SECURITY_BLOCK,"Reference dependency escapes its package")
            queue.append(target)
    return hashlib.sha256("\n".join(name+":"+value for name,value in sorted(seen.items())).encode()).hexdigest()
