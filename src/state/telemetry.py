import json
from datetime import datetime, timezone

from security.content import redact
from state.io import native_path


class Telemetry:
    def __init__(self, path):
        self.path = native_path(path)

    def record(self, event: str, **metrics):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = redact({"schema_version": "1.0", "time": datetime.now(timezone.utc).isoformat(), "event": event, **metrics})
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, allow_nan=False) + "\n")
            stream.flush()
