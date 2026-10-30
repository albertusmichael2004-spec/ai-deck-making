"""Live no-tool inference on synthetic consulting evidence, followed by independent QA."""
import importlib.util
from pathlib import Path
from uuid import uuid4

from knowledge.store import KnowledgeStore
from reasoning.engine import ReasoningEngine
from research.provider import CodexProvider
from state.errors import StudioError
from state.project import Project
from state.io import write_json

root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("reasoning_case",root/"tests/fixtures/reasoning_case.py")
case=importlib.util.module_from_spec(spec);spec.loader.exec_module(case)
project=Project.create(root,"reason-smoke-"+uuid4().hex[:10])
request,expected,store=case.prepare(root,project)
report={"schema_version":"1.0","passed":False,"project_id":project.path.name}
try:
    result=ReasoningEngine(root,project,KnowledgeStore(root),CodexProvider(root)).reason(**request)
    report.update({"passed":result["qa"]["passed"] and "material" in result["storyline"]["core_answer"]["text"].lower(),"core_answer":result["storyline"]["core_answer"],"usage":result["lineage"]["usage"],"qa":result["qa"]})
except StudioError as exc:report["failure"]=exc.as_dict()
write_json(root/"implementation/PHASE_REPORTS/phase_5_live_smoke.json",report)
print(__import__("json").dumps(report,indent=2))
raise SystemExit(0 if report["passed"] else 1)
