import re


def external_content(text: str, source_id: str) -> dict:
    """A data envelope, never a tool command or higher-priority instruction."""
    return {"source_id": source_id, "trust": "untrusted_data", "may_execute": False, "content": text}


_SENSITIVE = re.compile(r"(api[_-]?key|authorization|password|token|secret)", re.I)


def redact(value):
    if isinstance(value, dict):
        return {key: "[REDACTED]" if _SENSITIVE.search(str(key)) else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"(?i)(bearer\s+|sk-)[a-z0-9_\-.]+", "[REDACTED]", value)
    return value
