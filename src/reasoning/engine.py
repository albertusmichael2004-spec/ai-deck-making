import json
from copy import deepcopy
from uuid import uuid4

from evidence.store import EvidenceStore,identity
from evidence.verification import EvidenceVerifier
from ir.validation import validate
from reasoning.narrative import narrative_qa
from reasoning.planning import allocate
from reasoning.strategies import ModelReasoningStrategy
from state.errors import StudioError,ErrorCode
from state.io import read_json,write_json,fingerprint
from state.locking import FileLock


class ReasoningEngine:
    def __init__(self,repository,project,knowledge,provider=None,*,strategy=None):
        self.repository,self.project,self.knowledge,self.provider=repository,project,knowledge,provider
        self.strategy=strategy or ModelReasoningStrategy(provider)

    def reason(self,brief,coverage_keys,evidence_ids,appendix_budget=0,max_tokens=64000,analysis=None):
        validate(self.repository,"brief_spec",brief)
        if not coverage_keys or len(coverage_keys)!=len(set(coverage_keys)):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Decision coverage keys must be explicit and unique")
        if type(appendix_budget)!=int or not 0<=appendix_budget<brief["page_budget"]:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Invalid appendix allocation")
        if not evidence_ids:raise StudioError(ErrorCode.RESEARCH_INCOMPLETE,"Reasoning requires verified project evidence")
        if type(max_tokens)!=int or max_tokens<=0:raise StudioError(ErrorCode.RESEARCH_BUDGET_EXHAUSTED,"Reasoning requires a positive configured token budget")
        store=EvidenceStore(self.repository,self.project);graph=store.load();before=fingerprint(store.path)
        selected=[];seen=set();verifier=EvidenceVerifier(self.project.policy)
        for key in evidence_ids:
            for node in graph.trace(key):
                if node["status"]!="current":raise StudioError(ErrorCode.RESEARCH_INCOMPLETE,"Reasoning depends on stale or unverified evidence")
                if node["type"] in {"raw_fact","calculated_fact"}:verifier.value(graph,node["evidence_id"])
                if node["evidence_id"] not in seen:selected.append(node);seen.add(node["evidence_id"])
        guidance=self.knowledge.retrieve("MECE issue tree hypothesis Pyramid SCQA action titles "+brief["decision_required"],limit=8,kind="playbook")
        schema=read_json(self.repository/"schemas/storyline_graph/1.0.json")
        context={"brief":brief,"coverage_keys":coverage_keys,"analysis":analysis or {},"evidence":selected,"guidance":[{key:row[key] for key in ["chunk_id","title","text","source_sha256","knowledge_policy"]} for row in guidance]}
        story=self.strategy.propose(context,schema)
        usage=deepcopy(getattr(self.strategy,"last_usage",{"tokens":0}))
        if usage.get("tokens",0)>max_tokens:raise StudioError(ErrorCode.RESEARCH_BUDGET_EXHAUSTED,"Reasoning token budget reached",usage=usage)
        validate(self.repository,"storyline_graph",story)
        if story["decision_question"]!=brief["decision_required"]:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Reasoning changed the decision question")
        if any(key not in seen for row in story["arguments"] for key in row["evidence_ids"]):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Reasoning cited evidence outside its selected context")
        qa=narrative_qa(story,graph,self.project.policy,coverage_keys)
        write_json(self.project.path/"output/qa/narrative_qa.json",qa)
        if not qa["passed"]:raise StudioError(ErrorCode.QA_FAILURE,"Storyline failed narrative checks",findings=qa["findings"])
        plan=allocate(story,brief["page_budget"],appendix_budget)
        story["storyline_id"]="story_"+uuid4().hex
        with FileLock(self.project.policy.check(self.project.path/"work/evidence.lock",write=True)):
            if fingerprint(store.path)!=before:raise StudioError(ErrorCode.FILE_CONFLICT,"Evidence changed during reasoning")
            claim_ids={}
            for argument in story["arguments"]:
                key=identity("claim",story["storyline_id"]+":"+argument["argument_id"])
                graph.register({"evidence_id":key,"type":"interpretation","text":argument["claim"],"supported_by":argument["evidence_ids"],"confidence":min(graph.resolve(value)["confidence"] for value in argument["evidence_ids"]),"assumptions":[],"implication":argument["implication"]})
                claim_ids[argument["argument_id"]]=key
            recommendation_ids={}
            for recommendation in story["recommendations"]:
                key=identity("rec",story["storyline_id"]+":"+recommendation["recommendation_id"])
                graph.register({"evidence_id":key,"type":"recommendation","text":recommendation["text"],"supported_by":[claim_ids[value] for value in recommendation["argument_ids"]],"confidence":min(graph.resolve(claim_ids[value])["confidence"] for value in recommendation["argument_ids"]),"assumptions":recommendation["assumptions"]})
                recommendation_ids[recommendation["recommendation_id"]]=key
            store.save(graph)
            write_json(self.project.path/"state/storyline_graph.json",story)
            write_json(self.project.path/"state/storyline_plan.json",plan)
            lineage={"schema_version":"1.0","storyline_id":story["storyline_id"],"claim_ids":claim_ids,"recommendation_ids":recommendation_ids,"knowledge_ids":[row["chunk_id"] for row in guidance],"knowledge_provenance":[{key:row[key] for key in ["chunk_id","original_path","source_sha256","locator"]} for row in guidance],"usage":usage}
            write_json(self.project.path/"state/storyline_lineage.json",lineage)
        return {"storyline":story,"plan":plan,"lineage":lineage,"qa":qa}
