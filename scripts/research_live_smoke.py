"""Explicit public-data search/fetch/extract smoke, separate from deterministic tests."""
from pathlib import Path
from uuid import uuid4
from research.provider import CodexProvider
from research.fetch import PublicHTTPFetcher
from research.snapshot import extract_snapshot
from state.errors import StudioError
from state.io import write_json

root=Path(__file__).resolve().parents[1]
provider=CodexProvider(root)
report={"schema_version":"1.0","passed":False,"configured_model":provider.model}
try:
    hits=provider.search("site:science.nasa.gov/mars Mars mean radius kilometers official overview",2)
    report["search_usage"]=dict(provider.last_usage)
    report["search_results"]=hits
    document=PublicHTTPFetcher().fetch("https://science.nasa.gov/mars/facts/")
    question={"question_id":"mars_radius","question":"What is Mars mean radius in kilometers?","answer_type":"numeric","period":None,"geography":None,"definition":None}
    findings=provider.extract(document,question)
    report["extraction_usage"]=dict(provider.last_usage)
    extract_snapshot({"document":document,"findings":findings})
    report.update({"passed":bool(hits and findings),"findings":findings,"source_url":document["url"],"source_sha256":document["sha256"],"source_bytes":len(__import__("base64").b64decode(document["raw_base64"]))})
except StudioError as exc:report["failure"]=exc.as_dict()
write_json(root/"implementation/PHASE_REPORTS/phase_4_live_smoke.json",report)
print(__import__("json").dumps(report,indent=2))
raise SystemExit(0 if report["passed"] else 1)
