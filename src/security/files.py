import json
import io
import mimetypes
import shutil
import zipfile
from urllib.parse import urlsplit
from pathlib import Path, PurePosixPath
from contextlib import nullcontext

from state.errors import ErrorCode, StudioError
from state.io import sha256, write_json,open_read


class FileRegistry:
    """Inspect untrusted bytes before materializing an immutable project input."""
    def __init__(self, policy, limits: dict):
        self.policy, self.limits = policy, limits

    def inspect(self, path: Path, role: str) -> dict:
        path = self.policy.check(path)
        if not path.is_file():
            raise StudioError(ErrorCode.SOURCE_ACCESS_ERROR, "Source is not a readable file")
        if role not in self.limits["roles"]:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Unrecognized source role")
        if path.stat().st_size > self.limits["max_file_bytes"]:
            raise StudioError(ErrorCode.SECURITY_BLOCK, "File exceeds size limit")
        ext = path.suffix.lower()
        if ext not in self.limits["allowed_extensions"]:
            raise StudioError(ErrorCode.SECURITY_BLOCK, "File type is not allowlisted")
        with open_read(path) as stream:
            prefix = stream.read(16)
        if ext == ".pdf" and not prefix.startswith(b"%PDF-"):
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "PDF signature mismatch")
        if ext in {".png", ".jpg", ".jpeg"}:
            expected = prefix.startswith(b"\x89PNG\r\n\x1a\n") if ext == ".png" else prefix.startswith(b"\xff\xd8\xff")
            if not expected:
                raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Image signature mismatch")
        if ext in {".pptx", ".xlsx", ".docx", ".zip"}:
            self._inspect_archive(path, ext)
        elif ext in {".txt", ".md", ".csv", ".json", ".jsonl", ".yaml", ".yml"}:
            try:
                text = path.read_text(encoding="utf-8-sig")
                if "\x00" in text:
                    raise ValueError("binary content in text")
                if ext == ".json": json.loads(text)
                if ext == ".jsonl":
                    for line in text.splitlines():
                        if line.strip(): json.loads(line)
            except (ValueError, UnicodeError) as exc:
                raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Text content does not match declared format") from exc
        digest=sha256(path)
        return {"schema_version": "1.0", "source_id": "src_" + digest, "original_path": str(path), "sha256": digest, "bytes": path.stat().st_size, "mime": mimetypes.guess_type(path.name)[0] or "application/octet-stream", "role": role, "trust": "untrusted_data", "executable": False}

    def _inspect_archive(self, path, ext, depth=0, budget=None):
        if depth > self.limits["max_archive_depth"]:
            raise StudioError(ErrorCode.SECURITY_BLOCK, "Archive nesting limit exceeded")
        budget = budget if budget is not None else {"entries": 0, "bytes": 0}
        try:
            with (open_read(path) if isinstance(path,Path) else nullcontext(path)) as incoming,zipfile.ZipFile(incoming) as archive:
                infos = archive.infolist()
                budget["entries"] += len(infos)
                budget["bytes"] += sum(i.file_size for i in infos)
                if budget["entries"] > self.limits["max_archive_entries"]:
                    raise StudioError(ErrorCode.SECURITY_BLOCK, "Archive entry limit exceeded")
                if budget["bytes"] > self.limits["max_archive_expanded_bytes"]:
                    raise StudioError(ErrorCode.SECURITY_BLOCK, "Archive expansion limit exceeded")
                names = set()
                for entry in infos:
                    name = entry.filename.replace("\\", "/")
                    parts = PurePosixPath(name).parts
                    if name.startswith("/") or ".." in parts or any(":" in part for part in parts) or entry.flag_bits & 1:
                        raise StudioError(ErrorCode.SECURITY_BLOCK, "Unsafe archive member")
                    if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                        raise StudioError(ErrorCode.SECURITY_BLOCK, "Archive symlink is forbidden")
                    if entry.file_size / max(entry.compress_size, 1) > self.limits["max_compression_ratio"]:
                        raise StudioError(ErrorCode.SECURITY_BLOCK, "Suspicious compression ratio")
                    if name.lower() in names:
                        raise StudioError(ErrorCode.SECURITY_BLOCK, "Duplicate archive members")
                    names.add(name.lower())
                    if any(token in name.lower() for token in ["vbaproject", "activex/"]) or ("/embeddings/" in name.lower() and not name.lower().endswith(".xlsx")):
                        raise StudioError(ErrorCode.SECURITY_BLOCK, "Macro, OLE, or ActiveX content requires explicit review")
                    if "/embeddings/" in name.lower() and name.lower().endswith(".xlsx"):
                        # A native chart's inert data workbook is required editable evidence.
                        # Inspect it recursively; never execute it or follow data connections.
                        self._inspect_archive(io.BytesIO(archive.read(entry)), ".xlsx", depth + 1, budget)
                    if name.endswith(".rels"):
                        from xml.etree import ElementTree as ET
                        payload = archive.read(entry)
                        if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
                            raise StudioError(ErrorCode.SECURITY_BLOCK, "XML entities are forbidden")
                        tree = ET.fromstring(payload)
                        for relation in tree:
                            if relation.attrib.get("TargetMode") == "External":
                                if relation.attrib.get("Type", "").rsplit("/", 1)[-1] != "hyperlink":
                                    raise StudioError(ErrorCode.SECURITY_BLOCK, "External data relationships require explicit review")
                                if urlsplit(relation.attrib.get("Target", "")).scheme.lower() not in {"https", "http", "mailto"}:
                                    raise StudioError(ErrorCode.SECURITY_BLOCK, "Unsafe hyperlink scheme")
                expected = {".pptx": "ppt/presentation.xml", ".xlsx": "xl/workbook.xml", ".docx": "word/document.xml"}.get(ext)
                if expected and (expected not in names or "[content_types].xml" not in names):
                    raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "OOXML package type mismatch")
                if archive.testzip() is not None:
                    raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Archive checksum failure")
        except (zipfile.BadZipFile, ValueError) as exc:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Invalid archive") from exc

    def materialize(self, source: Path, destination: Path, role: str) -> dict:
        record = self.inspect(source, role)
        dest = self.policy.check(destination, write=True)
        if dest.exists():
            raise StudioError(ErrorCode.FILE_CONFLICT, "Input destination already exists")
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open_read(self.policy.check(source)) as incoming, dest.open("xb") as outgoing:
                shutil.copyfileobj(incoming, outgoing)
            if sha256(dest) != record["sha256"]:
                raise StudioError(ErrorCode.SOURCE_CONFLICT, "Source changed during materialization")
            record["materialized_path"] = str(dest)
            write_json(dest.with_name(dest.name + ".source.json"), record)
        except Exception:
            dest.unlink(missing_ok=True)
            raise
        return record
