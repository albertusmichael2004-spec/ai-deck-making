"""Translate a validated storyline into source-bound, answer-first file-mode IR."""
from copy import deepcopy

from evidence.context import EvidenceContext
from evidence.exhibits import CHARTS
from evidence.store import EvidenceStore,identity
from ir.validation import validate
from layout.chart_selection import select_chart
from reasoning.narrative import narrative_qa
from state.errors import StudioError,ErrorCode
from state.io import read_json,write_json,fingerprint
from state.locking import FileLock


class DesignPlanner:
    def __init__(self,repository,project):self.repository,self.project=repository,project

    def plan(self,brief,exhibits=None,brand_profile="default_consulting",canvas=None,template=None,reference_project=None):
        if reference_project is not None and reference_project!=self.project.path.name:
            raise StudioError(ErrorCode.SECURITY_BLOCK,"Reference scope must match the project explicitly selected for this task")
        from references.catalog import ReferenceCatalog
        references=ReferenceCatalog(self.repository,project_id=reference_project)
        validate(self.repository,"brief_spec",brief)
        story=read_json(self.project.path/"state/storyline_graph.json")
        plan=read_json(self.project.path/"state/storyline_plan.json")
        lineage=read_json(self.project.path/"state/storyline_lineage.json")
        validate(self.repository,"storyline_graph",story)
        if story["decision_question"]!=brief["decision_required"] or lineage["storyline_id"]!=story["storyline_id"] or plan["page_budget"]!=brief["page_budget"]:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Design brief/plan/lineage must match the validated storyline")
        store=EvidenceStore(self.repository,self.project);graph=store.load();before=fingerprint(store.path)
        coverage=sorted({key for issue in story["issues"] for key in issue["coverage_keys"]})
        qa=narrative_qa(story,graph,self.project.policy,coverage)
        if not qa["passed"]:raise StudioError(ErrorCode.QA_FAILURE,"Storyline is no longer supported",findings=qa["findings"])
        arguments={row["argument_id"]:row for row in story["arguments"]};exhibits=exhibits or {}
        if not set(exhibits)<=set(arguments):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Exhibit intent refers to an unknown argument")
        slides=[]
        for index,page in enumerate([*plan["main"],*plan["appendix"]]):
            slide_id="design_"+identity("page",story["storyline_id"]+":"+str(index)).split("_")[-1][:24]
            selected=[arguments[key] for key in page["argument_ids"]]
            claims=[lineage["claim_ids"][row["argument_id"]] for row in selected]
            for argument,claim_id in zip(selected,claims,strict=True):
                node=graph.resolve(claim_id)
                if node.get("text")!=argument["claim"] or set(node.get("supported_by",[]))!=set(argument["evidence_ids"]):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Storyline claim lineage differs from its registered interpretation")
            summary=page["role"]=="executive_summary"
            proposed=False
            exhibit={"type":"text","items":[{"title":row["action_title"],"body":row["claim"]} for row in selected]}
            if not summary:
                recommendation=next((row for row in story["recommendations"] if row["argument_ids"][-1]==selected[0]["argument_id"]),None)
                if recommendation:
                    proposed=True
                    exhibit={"type":"recommendation","items":[*[{"title":step["action"],"body":step["owner"]+"; "+step["timing"]} for step in recommendation["next_steps"]],{"title":"Decision conditions","body":"\n".join(recommendation["assumptions"])},{"title":"Tradeoffs to protect","body":"\n".join(recommendation["tradeoffs"])}]}
                exhibit=deepcopy(exhibits.get(selected[0]["argument_id"],exhibit))
                if "relationship" in exhibit:
                    relationship=exhibit.pop("relationship")
                    kind=select_chart(relationship,len(exhibit.get("category_evidence_ids",[])),len(exhibit.get("series",[])),any(float(graph.resolve(key)["value"])<0 for row in exhibit.get("series",[]) for key in row["evidence_ids"]))
                    if "type" in exhibit and exhibit["type"]!=kind:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Explicit chart type conflicts with analytical relationship")
                    exhibit["type"]=kind
            sources=set()
            used=[]
            if exhibit["type"] in CHARTS|{"table","matrix"}:
                used=[key for row in exhibit["rows"] for key in row] if exhibit["type"] in {"table","matrix"} else [*exhibit["category_evidence_ids"],*[key for row in exhibit["series"] for key in row["evidence_ids"]]]
                used=list(dict.fromkeys(used));binding_id=identity("binding",story["storyline_id"]+":"+slide_id)
                exhibit["binding_id"]=binding_id
                expected={"binding_id":binding_id,"evidence_ids":used,"slide_id":slide_id,"exhibit_id":"chart_"+slide_id}
                if binding_id in graph.value["bindings"]:
                    if graph.value["bindings"][binding_id]!=expected:raise StudioError(ErrorCode.FILE_CONFLICT,"Existing design binding differs; preserve the earlier design and supply a new storyline")
                else:graph.bind(binding_id,used,slide_id,expected["exhibit_id"])
            for key in [*claims,*used]:
                for node in graph.trace(key):
                    if node["type"]=="raw_fact":sources.add(node["source_id"])
            message=story["scqa"]["complication"] if summary else selected[0]["implication"]
            if proposed:message="Proposed action: "+message
            slides.append({"schema_version":"1.0","slide_id":slide_id,"purpose":page["role"],"action_title":page["title"],"key_message":message,"claim_ids":claims,"exhibit":exhibit,"layout":{"archetype":"executive_summary" if summary else "auto"},"insights":[],"source_note_ids":sorted(sources),"brand_profile":brand_profile})
        deck={"schema_version":"1.1" if template else "1.0","deck_id":story["storyline_id"],"brief_id":brief["brief_id"],"core_answer":story["core_answer"]["text"],"storyline":[row["purpose"] for row in slides],"slide_ids":[row["slide_id"] for row in slides],"canvas":canvas or {"width_in":13.333333,"height_in":7.5}}
        if template:deck["template"]=template
        validate(self.repository,"deck_spec",deck)
        # Validate layout and source payloads before making any binding durable.
        from layout.adaptive import AdaptiveLayoutCompiler
        from preferences.store import PreferenceStore
        layout=AdaptiveLayoutCompiler(self.repository,PreferenceStore(self.repository),{"user_id":"local","project_id":self.project.path.name});context=EvidenceContext(graph,self.project.policy)
        for slide in slides:
            validate(self.repository,"slide_spec",slide)
            notes=context.validate_slide(slide,brief["constraints"]["sources_required"])
            prepared=deepcopy(slide);prepared["exhibit"]=context.resolve_exhibit(slide)
            layout.compile(deck,prepared,notes)
        result={"brief":deepcopy(brief),"deck":deck,"slides":slides}
        candidates={"schema_version":"1.0","project_scope":reference_project,"trust":"untrusted_reference_data","purpose":"design_precedents_only","slides":[{"slide_id":slide["slide_id"],"candidates":references.query({"text":slide["action_title"],"brand":brand_profile},limit=4)} for slide in slides]}
        with FileLock(self.project.policy.check(self.project.path/"work/evidence.lock",write=True)):
            if fingerprint(store.path)!=before:raise StudioError(ErrorCode.FILE_CONFLICT,"Evidence changed during design planning")
            store.save(graph)
            write_json(self.project.path/"state/design_spec.json",result)
            write_json(self.project.path/"state/reference_candidates.json",candidates)
        return result
