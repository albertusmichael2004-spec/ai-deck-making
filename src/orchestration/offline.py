"""Durable offline build/review/repair/commit loop using existing transactions."""
import hashlib
import json
import shutil
import time
from uuid import uuid4

from evidence.context import EvidenceContext
from evidence.store import EvidenceStore
from layout.adaptive import AdaptiveLayoutCompiler
from orchestration.repair import PatchExecutor,RepairPlanner
from presentation.compiler.compiler import PresentationCompiler
from qa.regression import protected_scope
from qa.transaction import PresentationValidator
from state.errors import StudioError,ErrorCode
from state.io import read_json,write_json,sha256
from state.locking import FileLock
from state.project import artifact_id


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()


class OfflineLoop:
    def __init__(self,repository,project,backend,renderer,critic,repairer=None,layout=None):
        self.root,self.project,self.backend,self.renderer,self.critic=repository,project,backend,renderer,critic
        self.repairer=repairer or RepairPlanner(repository,critic.provider)
        self.layout=layout or AdaptiveLayoutCompiler(repository)

    def run(self,spec,*,scope=None,run_id=None,max_iterations=3,max_tokens=192000,max_seconds=900,max_cost_usd=None,initial_patch=None,previous_spec=None,changed_evidence_ids=()):
        if type(max_iterations)!=int or not 0<=max_iterations<=10 or type(max_tokens)!=int or max_tokens<=0 or type(max_seconds) not in {int,float} or not 0<max_seconds<=3600:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Invalid finite repair budgets")
        if max_cost_usd is not None and (type(max_cost_usd) not in {int,float} or not 0<max_cost_usd<10000):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Invalid cost budget")
        if max_cost_usd is not None and not getattr(self.critic.provider,"cost_telemetry_available",False):raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE,"A monetary budget requires measured provider cost telemetry")
        identifier=artifact_id(run_id) if run_id else uuid4().hex
        folder=self.project.policy.check(self.project.path/"work/offline_runs"/identifier,write=True)
        folder.mkdir(parents=True,exist_ok=True)
        if initial_patch is not None and previous_spec is not None or (initial_patch is not None or previous_spec is not None) and scope is None:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"An existing-deck revision requires one explicit patch or dependency refresh and trusted scope")
        request={"spec":spec,"scope":scope,"max_iterations":max_iterations,"max_tokens":max_tokens,"max_seconds":max_seconds,"max_cost_usd":max_cost_usd,"initial_patch":initial_patch,"previous_spec":previous_spec,"changed_evidence_ids":list(changed_evidence_ids)}
        with FileLock(folder/"run.lock"):
            call_started=time.monotonic();journal=folder/"run.json"
            previous_elapsed=read_json(journal)["elapsed_seconds"] if journal.exists() else 0
            try:return self._run(folder,identifier,request)
            except Exception as exc:
                if journal.exists():
                    state=read_json(journal)
                    state["elapsed_seconds"]=max(state["elapsed_seconds"],previous_elapsed+time.monotonic()-call_started)
                    state["last_error"]=exc.as_dict() if isinstance(exc,StudioError) else {"type":type(exc).__name__,"message":"Run interrupted; verify persisted candidate and intent before resume"}
                    if isinstance(exc,StudioError) and "usage" in exc.details:state["tokens"]+=exc.details["usage"].get("tokens",0)
                    write_json(journal,state)
                raise

    def _run(self,folder,identifier,request):
        started=time.monotonic();path=folder/"run.json";store=EvidenceStore(self.root,self.project)
        intent={key:value for key,value in request.items() if key not in {"initial_patch","previous_spec","changed_evidence_ids"} or value}
        if path.exists():
            state=read_json(path)
            if state["request_sha256"] not in {digest(intent),digest(request)}:raise StudioError(ErrorCode.FILE_CONFLICT,"Resume request differs from durable intent")
            if state["status"]=="committing":
                self.project.recover()
                if self.project.canonical.exists() and sha256(self.project.canonical)==state["candidate_sha256"] and self.project.state()["generation"]==state["base"]["generation"]+1:
                    state["status"]="committed";write_json(path,state)
                elif not self.project.detect_conflict(state["base"]):
                    journal=read_json(self.project.candidate(state["transaction_id"]).with_name("transaction.json"))
                    if journal["status"]=="aborted":state["transaction_id"]=self.project.begin()
                    elif journal["status"]!="planned":raise StudioError(ErrorCode.FILE_CONFLICT,"Interrupted commit cannot be safely replayed")
                    state["status"]="running";write_json(path,state)
            if state["status"]=="committed":
                if sha256(self.project.canonical)!=state["candidate_sha256"]:raise StudioError(ErrorCode.FILE_CONFLICT,"Committed deck has changed since this run")
                return {"passed":True,"no_op":True,"run_id":identifier,"state":state}
            if state["status"]!="running":return {"passed":False,"run_id":identifier,"state":state}
            if self.project.detect_conflict(state["base"]):raise StudioError(ErrorCode.FILE_CONFLICT,"User changed canonical before resume")
            candidate=self.project.policy.check(folder/state["candidate"])
            if sha256(candidate)!=state["candidate_sha256"]:raise StudioError(ErrorCode.FILE_CONFLICT,"Resume candidate was changed")
            spec=read_json(folder/state["spec"])
            context=EvidenceContext(store.load(),self.project.policy)
            if digest(context.graph.value)!=state["evidence_sha256"]:raise StudioError(ErrorCode.FILE_CONFLICT,"Evidence changed before resume")
        else:
            if self.project.canonical.exists() and request["initial_patch"] is None and request["previous_spec"] is None:raise StudioError(ErrorCode.SECURITY_BLOCK,"Existing decks require scoped patch or incremental refresh; whole-deck replacement is not a repair")
            transaction=self.project.begin();base=read_json(self.project.candidate(transaction).with_name("transaction.json"))["base"]
            spec=request["spec"];context=EvidenceContext(store.load(),self.project.policy)
            candidate=folder/"candidate_0.pptx"
            compiler=PresentationCompiler(self.root,self.layout,self.backend)
            if request["initial_patch"] is not None:
                from orchestration.repair import update_copy
                spec=update_copy(spec,self.backend.inspect(self.project.canonical),request["initial_patch"],context)
                initial_result=self.backend.patch(self.project.canonical,candidate,request["initial_patch"],request["scope"])
                if not initial_result["changed_targets"]:
                    self.project.abort(transaction)
                    return {"passed":True,"no_op":True,"run_id":identifier,"reason":"initial_patch_no_op"}
            elif request["previous_spec"] is not None:
                from presentation.compiler.incremental import IncrementalCompiler
                IncrementalCompiler(self.root,compiler).compile(self.project.canonical,candidate,request["previous_spec"],spec,context,request["changed_evidence_ids"],request["scope"])
            else:compiler.compile(**spec,destination=candidate,evidence=context)
            inspection=self.backend.inspect(candidate)
            declared={(s["slide_id"],o["object_id"]):o.get("protection","MAY_CHANGE") for s in spec["slides"] for o in s.get("objects",[])}
            scope=request["scope"] or {"objects":[{"slide_id":s["slide_id"],"object_id":o["object_id"],"protection":"MUST_NOT_CHANGE" if o.get("role")=="source" else declared.get((s["slide_id"],o["object_id"]),"MAY_CHANGE")} for s in inspection["slides"] for o in s["objects"]]}
            from ir.validation import validate
            validate(self.root,"edit_scope",scope)
            baseline=self.backend.inspect(self.project.canonical) if self.project.canonical.exists() else inspection
            write_json(folder/"baseline.json",baseline);write_json(folder/"spec_0.json",spec)
            state={"schema_version":"1.0","run_id":identifier,"transaction_id":transaction,"request_sha256":digest(intent),"base":base,"status":"running","iteration":0,"candidate":candidate.name,"candidate_sha256":sha256(candidate),"spec":"spec_0.json","evidence_sha256":digest(context.graph.value),"scope":scope,"tokens":0,"cost_usd":0,"elapsed_seconds":0,"history":[]}
            write_json(path,state)
        baseline=read_json(folder/"baseline.json")
        def persist():
            state["elapsed_seconds"]+=time.monotonic()-started
            write_json(path,state)
        def stop(reason):
            state.update(status="stopped",stop_reason=reason);persist()
            journal=read_json(self.project.candidate(state["transaction_id"]).with_name("transaction.json"))
            if journal["status"]=="planned":self.project.abort(state["transaction_id"])
            return {"passed":False,"run_id":identifier,"state":state}
        while True:
            if state["tokens"]>=request["max_tokens"] or state["elapsed_seconds"]+time.monotonic()-started>=request["max_seconds"]:return stop("token_or_latency_budget")
            if request["max_cost_usd"] is not None and state["cost_usd"]>=request["max_cost_usd"]:return stop("cost_budget")
            output=folder/("review_"+str(state["iteration"])+"_"+uuid4().hex)
            qa=PresentationValidator(self.root,self.backend,self.renderer,output,baseline,state["scope"],evidence=context,slide_specs=spec["slides"])(candidate)
            review=self.critic.evaluate(spec,candidate,self.backend.inspect(candidate),read_json(output/"render_report.json"),context,output=output/"critic_report.json",max_tokens=request["max_tokens"]-state["tokens"])
            state["tokens"]+=review["usage"].get("tokens",0)
            state["cost_telemetry_known"]="cost_usd" in review["usage"]
            if request["max_cost_usd"] is not None and "cost_usd" not in review["usage"]:return stop("cost_telemetry_unavailable")
            state["cost_usd"]+=review["usage"].get("cost_usd",0)
            findings=[*qa["issues"],*review["issues"]]
            signature=digest([(r["code"],r["slide_id"],r["object_id"],r["message"]) for r in findings if r["severity"] in {"BLOCKER","MAJOR"}])
            state["history"].append({"iteration":state["iteration"],"candidate_sha256":sha256(candidate),"qa_passed":qa["passed"],"critic_passed":review["passed"],"score":review["score"],"finding_signature":signature,"review_directory":str(output)})
            if state["tokens"]>request["max_tokens"] or state["elapsed_seconds"]+time.monotonic()-started>request["max_seconds"]:return stop("token_or_latency_budget")
            if request["max_cost_usd"] is not None and state["cost_usd"]>request["max_cost_usd"]:return stop("cost_budget")
            if qa["passed"] and review["passed"]:
                context.assert_current();expected=sha256(candidate)
                shutil.copy2(candidate,self.project.candidate(state["transaction_id"]))
                state.update(status="committing",candidate_sha256=expected);persist()
                def final_guard(value):
                    context.assert_current()
                    if sha256(value)!=expected or not protected_scope(baseline,self.backend.inspect(value),state["scope"])["passed"]:raise StudioError(ErrorCode.FILE_CONFLICT,"Post-review candidate changed")
                    return qa
                self.project.commit(state["transaction_id"],final_guard)
                state["status"]="committed";write_json(path,state)
                return {"passed":True,"no_op":False,"run_id":identifier,"state":state}
            if state["iteration"]>=request["max_iterations"]:return stop("iteration_budget")
            if len(state["history"])>1 and state["history"][-2]["finding_signature"]==signature and state["history"][-2]["score"]>=review["score"]:return stop("diminishing_improvement")
            plan=self.repairer.propose(spec,self.backend.inspect(candidate),findings,state["scope"])
            usage=getattr(getattr(self.repairer,"provider",None),"last_usage",{})
            state["tokens"]+=usage.get("tokens",0)
            if request["max_cost_usd"] is not None:
                if "cost_usd" not in usage:return stop("cost_telemetry_unavailable")
                state["cost_usd"]+=usage["cost_usd"]
            if state["tokens"]>=request["max_tokens"]:return stop("token_budget")
            write_json(folder/("patch_"+str(state["iteration"])+".json"),plan)
            next_candidate=folder/("candidate_"+str(state["iteration"]+1)+".pptx")
            revised,outcome=PatchExecutor(self.root,self.backend).apply(candidate,next_candidate,spec,plan,context,state["scope"])
            if outcome["no_op"]:return stop("no_op_repair")
            spec=revised;candidate=next_candidate;state["iteration"]+=1
            write_json(folder/("spec_"+str(state["iteration"])+".json"),spec)
            state.update(candidate=candidate.name,candidate_sha256=sha256(candidate),spec="spec_"+str(state["iteration"])+".json")
            # Immutable per-iteration candidates make a crash before this pointer write replayable.
            state["elapsed_seconds"]+=time.monotonic()-started;started=time.monotonic();write_json(path,state)
