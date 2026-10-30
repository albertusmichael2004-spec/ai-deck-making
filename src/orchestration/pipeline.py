"""Plan and prepare verified evidence/storyline once, then run the offline loop."""
from pathlib import Path

from evidence.store import EvidenceStore
from knowledge.store import KnowledgeStore
from orchestration.offline import OfflineLoop,digest
from presentation.backends.ooxml import OOXMLBackend
from presentation.compiler.design import DesignPlanner
from presentation.rendering.native import NativeRenderer
from qa.critic import Critic
from reasoning.engine import ReasoningEngine
from reasoning.strategies import DriverReasoningStrategy
from research.engine import ResearchEngine
from research.fetch import PublicHTTPFetcher
from research.plan import ResearchPlanner
from state.errors import StudioError,ErrorCode
from state.io import read_json,write_json


class OfflinePipeline:
    def __init__(self,repository,project,provider):self.root,self.project,self.provider=repository,project,provider

    def execute(self,request,*,run_id=None):
        allowed={"brief","sources","research","reasoning","exhibit_intents","budgets","scope","reference_project"}
        if set(request)-allowed or not {"brief","reasoning"}<=set(request):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Invalid offline request fields")
        if request.get("reference_project") is not None and request["reference_project"]!=self.project.path.name:
            raise StudioError(ErrorCode.SECURITY_BLOCK,"Reference project must match the explicit project for this request")
        intent=self.project.path/"state/offline_request.json";spec_path=self.project.path/"state/offline_prepared_spec.json"
        knowledge=KnowledgeStore(self.root)
        if intent.exists():
            if read_json(intent)["request_sha256"]!=digest(request):raise StudioError(ErrorCode.FILE_CONFLICT,"Existing offline preparation belongs to a different request")
        else:write_json(intent,{"request_sha256":digest(request)})
        if spec_path.exists():spec=read_json(spec_path)
        else:
            store=EvidenceStore(self.root,self.project)
            for source in request.get("sources",[]):
                row=dict(source);path=Path(row.pop("path"));store.ingest(path,**row)
            if request.get("research"):
                plan=ResearchPlanner(self.root).plan(**request["research"])
                result=ResearchEngine(self.root,self.project,self.provider,PublicHTTPFetcher(),self.provider).run(plan)
                if not result.get("complete"):raise StudioError(ErrorCode.RESEARCH_INCOMPLETE,"Offline research has not met its evidence gate")
            reasoning=dict(request["reasoning"]);strategy=reasoning.pop("strategy","model")
            if strategy not in {"driver","model"}:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Unknown reasoning strategy")
            if not reasoning.get("evidence_ids"):reasoning["evidence_ids"]=[key for key,node in store.load().value["nodes"].items() if node["type"]=="raw_fact" and node["status"]=="current"]
            engine=ReasoningEngine(self.root,self.project,knowledge,self.provider,strategy=DriverReasoningStrategy() if strategy=="driver" else None)
            engine.reason(request["brief"],**reasoning)
            spec=DesignPlanner(self.root,self.project).plan(request["brief"],request.get("exhibit_intents",{}),reference_project=request.get("reference_project"));write_json(spec_path,spec)
        critic=Critic(self.root,self.provider,knowledge)
        loop=OfflineLoop(self.root,self.project,OOXMLBackend(self.root),NativeRenderer(self.root),critic)
        return loop.run(spec,scope=request.get("scope"),run_id=run_id,**request.get("budgets",{}))
