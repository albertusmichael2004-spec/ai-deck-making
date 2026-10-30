"""Refresh data, revalidate reasoning and retain stable slide/object identities."""
from copy import deepcopy

from evidence.store import EvidenceStore,identity
from presentation.compiler.design import DesignPlanner
from reasoning.engine import ReasoningEngine
from state.errors import StudioError,ErrorCode
from state.io import write_json,fingerprint
from state.locking import FileLock


class AnalyticalRefresh:
    def __init__(self,repository,project,knowledge,provider=None,*,strategy=None):
        self.root,self.project,self.knowledge,self.provider,self.strategy=repository,project,knowledge,provider,strategy

    def prepare(self,previous,source_ids,reasoning,exhibit_intents=None):
        store=EvidenceStore(self.root,self.project);affected=set()
        for key in source_ids:affected.update(store.refresh(key)["affected"])
        if not affected:return {"passed":True,"no_op":True,"spec":deepcopy(previous),"changed_evidence_ids":[]}
        reasoning=deepcopy(reasoning)
        reasoning.setdefault("appendix_budget",sum(slide["purpose"]=="appendix" for slide in previous["slides"]))
        ReasoningEngine(self.root,self.project,self.knowledge,self.provider,strategy=self.strategy).reason(previous["brief"],**reasoning)
        deck=previous["deck"]
        current=DesignPlanner(self.root,self.project).plan(previous["brief"],exhibit_intents,previous["slides"][0]["brand_profile"],deck["canvas"],deck.get("template"))
        if len(current["slides"])!=len(previous["slides"]) or [s["purpose"] for s in current["slides"]]!=[s["purpose"] for s in previous["slides"]]:raise StudioError(ErrorCode.USER_ACTION_REQUIRED,"Refreshed storyline needs structural slide changes; explicit new scope is required")
        graph=store.load();before=fingerprint(store.path)
        revised={"brief":deepcopy(previous["brief"]),"deck":{**deepcopy(deck),"core_answer":current["deck"]["core_answer"],"storyline":current["deck"]["storyline"]},"slides":[]}
        for old,new in zip(previous["slides"],current["slides"],strict=True):
            slide=deepcopy(new);slide["slide_id"]=old["slide_id"]
            binding=graph.value["bindings"].get(slide["exhibit"].get("binding_id"))
            if binding:
                binding_id=identity("binding",binding["binding_id"]+":"+old["slide_id"])
                if binding_id not in graph.value["bindings"]:graph.bind(binding_id,binding["evidence_ids"],old["slide_id"],"chart_"+old["slide_id"])
                slide["exhibit"]["binding_id"]=binding_id
            revised["slides"].append(slide)
        with FileLock(self.project.path/"work/evidence.lock"):
            if fingerprint(store.path)!=before:raise StudioError(ErrorCode.FILE_CONFLICT,"Evidence changed during analytical rebinding")
            store.save(graph)
            write_json(self.project.path/"state/analytical_refresh_spec.json",revised)
            result={"passed":True,"no_op":False,"spec":revised,"changed_evidence_ids":sorted(affected),"previous_claims_retained_as_stale":True}
            write_json(self.project.path/"state/analytical_refresh.json",result)
        return result
