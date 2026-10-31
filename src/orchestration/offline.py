"""Durable offline build/review/repair/commit loop using existing transactions."""
import hashlib
import json
import operator
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
        started=time.monotonic();store=EvidenceStore(self.root,self.project)
        intent={key:value for key,value in request.items() if key not in {"initial_patch","previous_spec","changed_evidence_ids"} or value}
        prepare=self._resume if (folder/"run.json").exists() else self._start
        result,session=prepare(folder,identifier,request,intent,store,started)
        if result is not None:return result
        state=session.state;baseline=read_json(folder/"baseline.json")
        while True:
            reason=self._budget_exceeded(session,request,operator.ge)
            if reason:return self._stop(session,reason)
            output=folder/("review_"+str(state["iteration"])+"_"+uuid4().hex)
            qa,review,reason=self._review(session,request,baseline,output)
            if reason:return self._stop(session,reason)
            findings=[*qa["issues"],*review["issues"]]
            signature=digest([(r["code"],r["slide_id"],r["object_id"],r["message"]) for r in findings if r["severity"] in {"BLOCKER","MAJOR"}])
            state["history"].append({"iteration":state["iteration"],"candidate_sha256":sha256(session.candidate),"qa_passed":qa["passed"],"critic_passed":review["passed"],"score":review["score"],"finding_signature":signature,"review_directory":str(output)})
            reason=self._budget_exceeded(session,request,operator.gt)
            if reason:return self._stop(session,reason)
            if qa["passed"] and review["passed"]:return self._commit(session,baseline,qa)
            if state["iteration"]>=request["max_iterations"]:return self._stop(session,"iteration_budget")
            if len(state["history"])>1 and state["history"][-2]["finding_signature"]==signature and state["history"][-2]["score"]>=review["score"]:return self._stop(session,"diminishing_improvement")
            reason=self._repair(folder,session,request,findings)
            if reason:return self._stop(session,reason)

    def _resume(self,folder,identifier,request,intent,store,started):
        """Reload a durable run; returns (final_result, None) or (None, session)."""
        path=folder/"run.json";state=read_json(path)
        if state["request_sha256"] not in {digest(intent),digest(request)}:raise StudioError(ErrorCode.FILE_CONFLICT,"Resume request differs from durable intent")
        if state["status"]=="committing":self._reconcile_commit(path,state)
        if state["status"]=="committed":
            if sha256(self.project.canonical)!=state["candidate_sha256"]:raise StudioError(ErrorCode.FILE_CONFLICT,"Committed deck has changed since this run")
            return {"passed":True,"no_op":True,"run_id":identifier,"state":state},None
        if state["status"]!="running":return {"passed":False,"run_id":identifier,"state":state},None
        if self.project.detect_conflict(state["base"]):raise StudioError(ErrorCode.FILE_CONFLICT,"User changed canonical before resume")
        candidate=self.project.policy.check(folder/state["candidate"])
        if sha256(candidate)!=state["candidate_sha256"]:raise StudioError(ErrorCode.FILE_CONFLICT,"Resume candidate was changed")
        spec=read_json(folder/state["spec"])
        context=EvidenceContext(store.load(),self.project.policy)
        if digest(context.graph.value)!=state["evidence_sha256"]:raise StudioError(ErrorCode.FILE_CONFLICT,"Evidence changed before resume")
        return None,_Session(path,identifier,state,spec,context,candidate,started)

    def _reconcile_commit(self,path,state):
        """Settle a run interrupted while committing: mark it committed or reopen it for review."""
        self.project.recover()
        if self.project.canonical.exists() and sha256(self.project.canonical)==state["candidate_sha256"] and self.project.state()["generation"]==state["base"]["generation"]+1:
            state["status"]="committed";write_json(path,state)
        elif not self.project.detect_conflict(state["base"]):
            journal=read_json(self.project.candidate(state["transaction_id"]).with_name("transaction.json"))
            if journal["status"]=="aborted":state["transaction_id"]=self.project.begin()
            elif journal["status"]!="planned":raise StudioError(ErrorCode.FILE_CONFLICT,"Interrupted commit cannot be safely replayed")
            state["status"]="running";write_json(path,state)

    def _start(self,folder,identifier,request,intent,store,started):
        """Open a transaction and persist candidate 0; returns (final_result, None) or (None, session)."""
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
                return {"passed":True,"no_op":True,"run_id":identifier,"reason":"initial_patch_no_op"},None
        elif request["previous_spec"] is not None:
            from presentation.compiler.incremental import IncrementalCompiler
            IncrementalCompiler(self.root,compiler).compile(self.project.canonical,candidate,request["previous_spec"],spec,context,request["changed_evidence_ids"],request["scope"])
        else:compiler.compile(**spec,destination=candidate,evidence=context)
        inspection=self.backend.inspect(candidate)
        scope=request["scope"] or default_scope(spec,inspection)
        from ir.validation import validate
        validate(self.root,"edit_scope",scope)
        baseline=self.backend.inspect(self.project.canonical) if self.project.canonical.exists() else inspection
        write_json(folder/"baseline.json",baseline);write_json(folder/"spec_0.json",spec)
        state={"schema_version":"1.0","run_id":identifier,"transaction_id":transaction,"request_sha256":digest(intent),"base":base,"status":"running","iteration":0,"candidate":candidate.name,"candidate_sha256":sha256(candidate),"spec":"spec_0.json","evidence_sha256":digest(context.graph.value),"scope":scope,"tokens":0,"cost_usd":0,"elapsed_seconds":0,"history":[]}
        path=folder/"run.json";write_json(path,state)
        return None,_Session(path,identifier,state,spec,context,candidate,started)

    @staticmethod
    def _budget_exceeded(session,request,reached):
        """Name the exhausted budget; `reached` is operator.ge before a review and operator.gt after it."""
        state=session.state
        if reached(state["tokens"],request["max_tokens"]) or reached(session.elapsed(),request["max_seconds"]):return "token_or_latency_budget"
        if request["max_cost_usd"] is not None and reached(state["cost_usd"],request["max_cost_usd"]):return "cost_budget"
        return None

    def _review(self,session,request,baseline,output):
        """Run deterministic QA and the Critic on the current candidate; returns (qa, review, stop_reason)."""
        state,candidate=session.state,session.candidate
        qa=PresentationValidator(self.root,self.backend,self.renderer,output,baseline,state["scope"],evidence=session.context,slide_specs=session.spec["slides"])(candidate)
        review=self.critic.evaluate(session.spec,candidate,self.backend.inspect(candidate),read_json(output/"render_report.json"),session.context,output=output/"critic_report.json",max_tokens=request["max_tokens"]-state["tokens"])
        state["tokens"]+=review["usage"].get("tokens",0)
        state["cost_telemetry_known"]="cost_usd" in review["usage"]
        if request["max_cost_usd"] is not None and "cost_usd" not in review["usage"]:return qa,review,"cost_telemetry_unavailable"
        state["cost_usd"]+=review["usage"].get("cost_usd",0)
        return qa,review,None

    def _commit(self,session,baseline,qa):
        state,candidate,context=session.state,session.candidate,session.context
        context.assert_current();expected=sha256(candidate)
        shutil.copy2(candidate,self.project.candidate(state["transaction_id"]))
        state.update(status="committing",candidate_sha256=expected);session.persist()
        def final_guard(value):
            context.assert_current()
            if sha256(value)!=expected or not protected_scope(baseline,self.backend.inspect(value),state["scope"])["passed"]:raise StudioError(ErrorCode.FILE_CONFLICT,"Post-review candidate changed")
            return qa
        self.project.commit(state["transaction_id"],final_guard)
        state["status"]="committed";write_json(session.path,state)
        return {"passed":True,"no_op":False,"run_id":session.identifier,"state":state}

    def _repair(self,folder,session,request,findings):
        """Propose and apply one scoped repair; returns a stop reason, or None after checkpointing the next candidate."""
        state=session.state
        plan=self.repairer.propose(session.spec,self.backend.inspect(session.candidate),findings,state["scope"])
        usage=getattr(getattr(self.repairer,"provider",None),"last_usage",{})
        state["tokens"]+=usage.get("tokens",0)
        if request["max_cost_usd"] is not None:
            if "cost_usd" not in usage:return "cost_telemetry_unavailable"
            state["cost_usd"]+=usage["cost_usd"]
        if state["tokens"]>=request["max_tokens"]:return "token_budget"
        write_json(folder/("patch_"+str(state["iteration"])+".json"),plan)
        next_candidate=folder/("candidate_"+str(state["iteration"]+1)+".pptx")
        revised,outcome=PatchExecutor(self.root,self.backend).apply(session.candidate,next_candidate,session.spec,plan,session.context,state["scope"])
        if outcome["no_op"]:return "no_op_repair"
        session.spec=revised;session.candidate=next_candidate;state["iteration"]+=1
        write_json(folder/("spec_"+str(state["iteration"])+".json"),revised)
        state.update(candidate=next_candidate.name,candidate_sha256=sha256(next_candidate),spec="spec_"+str(state["iteration"])+".json")
        # Immutable per-iteration candidates make a crash before this pointer write replayable.
        session.checkpoint()
        return None

    def _stop(self,session,reason):
        state=session.state
        state.update(status="stopped",stop_reason=reason);session.persist()
        journal=read_json(self.project.candidate(state["transaction_id"]).with_name("transaction.json"))
        if journal["status"]=="planned":self.project.abort(state["transaction_id"])
        return {"passed":False,"run_id":session.identifier,"state":state}


def default_scope(spec,inspection):
    """Protect source objects; otherwise use each object's declared protection (MAY_CHANGE by default)."""
    declared={(s["slide_id"],o["object_id"]):o.get("protection","MAY_CHANGE") for s in spec["slides"] for o in s.get("objects",[])}
    return {"objects":[{"slide_id":s["slide_id"],"object_id":o["object_id"],"protection":"MUST_NOT_CHANGE" if o.get("role")=="source" else declared.get((s["slide_id"],o["object_id"]),"MAY_CHANGE")} for s in inspection["slides"] for o in s["objects"]]}


class _Session:
    """One run's durable journal, working spec/candidate and wall-clock accounting since `started`."""
    def __init__(self,path,identifier,state,spec,context,candidate,started):
        self.path,self.identifier,self.state=path,identifier,state
        self.spec,self.context,self.candidate,self.started=spec,context,candidate,started

    def elapsed(self):return self.state["elapsed_seconds"]+time.monotonic()-self.started

    def persist(self):
        self.state["elapsed_seconds"]+=time.monotonic()-self.started
        write_json(self.path,self.state)

    def checkpoint(self):
        self.state["elapsed_seconds"]+=time.monotonic()-self.started;self.started=time.monotonic()
        write_json(self.path,self.state)
