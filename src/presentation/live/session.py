"""Live authority, scoped preflight/review, guarded mutation and durable recovery."""
import shutil
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from evidence.context import EvidenceContext
from evidence.store import EvidenceStore
from ir.validation import validate
from orchestration.repair import update_copy
from presentation.backends.ooxml import OOXMLBackend
from presentation.live.inspection import digest,now
from presentation.mutation.scope import validate_scope
from qa.regression import protected_scope
from qa.transaction import PresentationValidator
from state.errors import StudioError,ErrorCode
from state.io import read_json,write_json,write_yaml,fingerprint,sha256,native_path
from state.locking import FileLock


def objects(inspection):return {(slide["slide_id"],obj["object_id"]):obj for slide in inspection["slides"] for obj in slide["objects"]}


def replace_range(text,scope,replacement):
    value=text.replace("\r","\n");expected=scope["text"].replace("\r","\n")
    data=value.encode("utf-16-le");start=(scope["start"]-1)*2;end=start+scope["length"]*2
    if data[start:end].decode("utf-16-le")!=expected:raise StudioError(ErrorCode.LIVE_SELECTION_STALE,"Snapshot text no longer matches captured selection")
    return (data[:start]+replacement.encode("utf-16-le")+data[end:]).decode("utf-16-le")


class LiveSession:
    def __init__(self,repository,project,backend):
        self.root,self.project,self.backend=repository,project,backend
        self.path=project.path/"state/live_session.json";self.lock=project.path/"work/live_session.lock"

    def attach(self,save_policy="manual"):
        if save_policy not in {"manual","save_copy","save_existing"}:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Explicit save policy required")
        inspection=self.backend.inspect()
        self.project.policy.check(Path(getattr(self.backend,"local_target",self.backend.target)),write=True)
        with self.project._lock():
            state=self.project.state()
            if state["authority"]=="live":
                session=read_json(self.path)
                if session["status"]!="active" or session["target"]!=inspection["full_name"]:raise StudioError(ErrorCode.LIVE_PRESENTATION_CONFLICT,"Another live target owns the project")
                if session["save_policy"]!=save_policy:raise StudioError(ErrorCode.FILE_CONFLICT,"Existing live session has a different explicit save policy")
                return session
            canonical_target=native_path(Path(getattr(self.backend,"local_target",self.backend.target)))==native_path(self.project.canonical)
            current_disk=getattr(self.backend,"disk_fingerprint",None) if canonical_target else fingerprint(self.project.canonical)
            # A locked canonical remains protected by live authority. Its disk hash
            # is explicitly unverified; inspection/mutation use the actual memory snapshot.
            if current_disk is not None and current_disk!=state["canonical_fingerprint"]:raise StudioError(ErrorCode.FILE_CONFLICT,"Canonical changed before live authority acquisition")
            session={"schema_version":"1.0","session_id":uuid4().hex,"project_id":state["project_id"],"target":inspection["full_name"],"presentation_id":digest(inspection["full_name"].casefold()),"generation_id":uuid4().hex,"status":"active","save_policy":save_policy,"base_disk":current_disk or state["canonical_fingerprint"],"target_disk_fingerprint":getattr(self.backend,"disk_fingerprint",None),"last_live_fingerprint":inspection["fingerprint"],"history":[{"event":"attached","at":now(),"saved":inspection["saved"],"canonical_disk_verified":current_disk is not None}]}
            validate(self.root,"live_session",session);write_json(self.path,session)
            state["authority"]="live";write_yaml(self.project.state_path,state)
            return session

    def state(self):
        state=read_json(self.path);validate(self.root,"live_session",state)
        if state["status"]!="active" or self.project.state()["authority"]!="live" or state["target"]!=self.backend.target:raise StudioError(ErrorCode.LIVE_PRESENTATION_CONFLICT,"Live session/target is no longer authoritative")
        if "target_disk_fingerprint" in state:self.backend.disk_fingerprint=state["target_disk_fingerprint"]
        return state

    def selection(self):
        state=self.state();context=self.backend.selection(state["generation_id"])
        validate(self.root,"selection_context",context);return context

    def _require_resolved_transactions(self):
        pending=[]
        for path in (self.project.path/"work/live_transactions").glob("*/transaction.json"):
            value=read_json(path)
            if value["status"] in {"applying","recovery_required","recovery_conflict"}:pending.append(value["transaction_id"])
        if pending:raise StudioError(ErrorCode.USER_ACTION_REQUIRED,"Resolve retained live transaction recovery before mutation, saving or releasing authority",transaction_ids=pending)

    def _review(self,spec,snapshot,directory,context,critic,before=None,scope=None):
        backend=OOXMLBackend(self.root);source=Path(snapshot)
        qa=PresentationValidator(self.root,backend,self.backend,directory,before,scope,evidence=context,slide_specs=spec["slides"])(source)
        review=critic.evaluate(spec,source,backend.inspect(source),read_json(directory/"render_report.json"),context,output=directory/"critic_report.json")
        if not qa["passed"] or not review["passed"]:raise StudioError(ErrorCode.QA_FAILURE,"Live revision failed deterministic/semantic review",qa=qa,critic=review)
        return {"qa":qa,"critic":review}

    def apply(self,patch,scope,spec,critic,*,selection=None,copy_path=None,transaction_id=None):
        validate(self.root,"patch_spec",patch);validate(self.root,"edit_scope",scope);validate_scope(patch,scope)
        file_only={row["operation"] for row in patch["operations"]}&{"set_gradient_fill","connector_to_shape","set_chart_colors"}
        if file_only:
            raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE,"Use the Studio file revision workflow for these styles: save the working deck, release live authority, then use studio revise PROJECT --patch FILE --scope FILE with patch_spec 1.2, or a patch_plan 1.1 in the run workflow. Live rollback does not support these styles.",operations=sorted(file_only),workflow="file_revision",permission_exception_required=False)
        identifier=transaction_id or uuid4().hex
        from state.project import artifact_id
        artifact_id(identifier)
        folder=self.project.path/"work/live_transactions"/identifier;folder.mkdir(parents=True,exist_ok=True)
        journal_path=folder/"transaction.json"
        with FileLock(self.lock):
            session=self.state();request=digest({"patch":patch,"scope":scope,"spec":spec,"selection":selection,"copy_path":str(copy_path) if copy_path else None})
            if journal_path.exists():
                prior=read_json(journal_path)
                if prior["request_sha256"]!=request:raise StudioError(ErrorCode.FILE_CONFLICT,"Live transaction replay differs from its intent")
                if prior["status"]=="applied":return {"passed":True,"no_op":True,"transaction_id":identifier,"journal":prior}
                raise StudioError(ErrorCode.LIVE_PRESENTATION_CONFLICT,"Interrupted live transaction requires recover before new mutation")
            self._require_resolved_transactions()
            before=self.backend.inspect();before_objects=objects(before)
            if selection:
                validate(self.root,"selection_context",selection)
                if selection["generation_id"]!=session["generation_id"] or selection["presentation_id"]!=session["presentation_id"]:raise StudioError(ErrorCode.LIVE_SELECTION_STALE,"Selection belongs to another live generation")
                selected={(row["slide_id"],row["object_id"]):row for row in selection["objects"]}
                for operation in patch["operations"]:
                    key=(operation["slide_id"],operation["object_id"])
                    if key not in selected or operation["expected_fingerprint"]!=selected[key]["fingerprint"]:raise StudioError(ErrorCode.SECURITY_BLOCK,"Operation exceeds the captured selection")
                    if selection["text_scope"] is not None and operation["operation"]!="set_text":raise StudioError(ErrorCode.SECURITY_BLOCK,"A selected text range cannot silently broaden into an object design edit")
            for operation in patch["operations"]:
                key=(operation["slide_id"],operation["object_id"])
                if key not in before_objects or before_objects[key]["fingerprint"]!=operation["expected_fingerprint"]:raise StudioError(ErrorCode.LIVE_SELECTION_STALE,"User changed a target during planning")
            snapshot=self.backend.snapshot();source=Path(snapshot["path"])
            retained=folder/"before.pptx";shutil.copy2(source,retained)
            file_backend=OOXMLBackend(self.root);file_before=file_backend.inspect(retained);file_objects=objects(file_before)
            spec=deepcopy(spec)
            for declared,observed in zip(spec["slides"],file_before["slides"],strict=True):
                if declared["slide_id"]!=observed["slide_id"]:raise StudioError(ErrorCode.LIVE_PRESENTATION_CONFLICT,"Live snapshot ordering differs from declared intent; re-inspect before planning")
                titles=[obj["text"] for obj in observed["objects"] if obj.get("role")=="title"]
                bodies=[obj["text"] for obj in observed["objects"] if obj.get("role")=="body"]
                if titles:declared["action_title"]=" ".join(titles[0].split())
                if bodies:declared["key_message"]=" ".join(bodies[0].split())
            candidate=folder/"candidate.pptx";project_context=EvidenceContext(EvidenceStore(self.root,self.project).load(),self.project.policy)
            prepared=deepcopy(patch)
            for operation in prepared["operations"]:
                key=(operation["slide_id"],operation["object_id"])
                if key not in file_objects:raise StudioError(ErrorCode.LIVE_PRESENTATION_CONFLICT,"Native snapshot identity differs from captured target")
                operation["expected_fingerprint"]=file_objects[key]["fingerprint"]
                if selection and selection["text_scope"] and operation["operation"]=="set_text":operation["value"]=replace_range(file_objects[key]["text"],selection["text_scope"],operation["value"])
            revised=update_copy(spec,file_before,prepared,project_context)
            outcome=file_backend.patch(retained,candidate,prepared,scope)
            if not outcome["changed_targets"]:return {"passed":True,"no_op":True,"transaction_id":identifier}
            planned=self._review(revised,candidate,folder/"planned_review",project_context,critic,file_before,scope)
            if self.backend.inspect()["fingerprint"]!=before["fingerprint"]:raise StudioError(ErrorCode.LIVE_PRESENTATION_CONFLICT,"User changed the live presentation during QA/planning")
            journal={"schema_version":"1.0","transaction_id":identifier,"session_id":session["session_id"],"request_sha256":request,"status":"applying","before":before,"before_snapshot":str(retained),"before_snapshot_sha256":sha256(retained),"patch":patch,"scope":scope,"spec":revised,"selection":selection,"applied_objects":{},"planned_review":planned,"save_policy":session["save_policy"]}
            write_json(journal_path,journal)
            journal["autosave_policy"]=self.backend.pause_autosave();self._write_journal(journal_path,journal)
            try:
                for operation in patch["operations"]:
                    current=self.backend.inspect()
                    if current["canvas_pt"]!=before["canvas_pt"] or [(s["slide_id"],s.get("native_slide_id")) for s in current["slides"]]!=[(s["slide_id"],s.get("native_slide_id")) for s in before["slides"]]:raise StudioError(ErrorCode.LIVE_PRESENTATION_CONFLICT,"User changed canvas or slide structure immediately before mutation")
                    expected=deepcopy(before_objects)
                    expected.update(journal["applied_objects"])
                    actual=objects(current)
                    if any(key not in actual or actual[key]["fingerprint"]!=value["fingerprint"] for key,value in expected.items()) or actual.keys()!=expected.keys():raise StudioError(ErrorCode.LIVE_PRESENTATION_CONFLICT,"Concurrent user edit detected immediately before mutation")
                    key=(operation["slide_id"],operation["object_id"])
                    journal["pending_operation"]={"slide_id":key[0],"object_id":key[1]};self._write_journal(journal_path,journal)
                    rebased={**operation,"expected_fingerprint":actual[key]["fingerprint"]}
                    updated=self.backend.apply(rebased,text_scope=selection["text_scope"] if selection and operation["operation"]=="set_text" else None)
                    # JSON keys use an unambiguous index; the entire observed object remains recoverable.
                    journal["applied_objects"][key]=objects(updated)[key]
                    journal["pending_operation"]=None
                    self._write_journal(journal_path,journal)
                after=self.backend.inspect()
                if not protected_scope(before,after,scope)["passed"]:raise StudioError(ErrorCode.LIVE_PRESENTATION_CONFLICT,"A protected live object changed")
                post=self.backend.snapshot();post_path=folder/"after.pptx";shutil.copy2(Path(post["path"]),post_path)
                reviewed=self._review(revised,post_path,folder/"applied_review",project_context,critic,file_before,scope)
                if self.backend.inspect()["fingerprint"]!=after["fingerprint"]:raise StudioError(ErrorCode.LIVE_PRESENTATION_CONFLICT,"User edited live state during post-apply QA")
                saved=self.backend.save(session["save_policy"],copy_path=copy_path)
                journal["autosave_restored"]=self.backend.restore_autosave(journal["autosave_policy"])
                journal.update(status="applied",after_snapshot=str(post_path),after_snapshot_sha256=sha256(post_path),after_fingerprint=after["fingerprint"],applied_review=reviewed,save_result=saved)
                self._write_journal(journal_path,journal)
                session["target_disk_fingerprint"]=getattr(self.backend,"disk_fingerprint",None)
                session["last_valid_snapshot"]={"path":str(post_path),"sha256":sha256(post_path)}
                if journal["autosave_policy"].get("initial"):session["autosave_policy"]=journal["autosave_policy"]
                write_json(self.project.path/"state/live_spec.json",revised)
                session["generation_id"]=uuid4().hex;session["last_live_fingerprint"]=after["fingerprint"];session["history"].append({"event":"applied","transaction_id":identifier,"at":now()});write_json(self.path,session)
                return {"passed":True,"no_op":False,"transaction_id":identifier,"journal":self._serialized(journal)}
            except Exception:
                journal["status"]="recovery_required";self._write_journal(journal_path,journal)
                raise

    @staticmethod
    def _serialized(journal):
        result=deepcopy(journal);result["applied_objects"]=[{"slide_id":key[0],"object_id":key[1],"state":value} for key,value in journal["applied_objects"].items()]
        return result

    def _write_journal(self,path,journal):write_json(path,self._serialized(journal))

    def recover(self,transaction_id):
        from state.project import artifact_id
        folder=self.project.path/"work/live_transactions"/artifact_id(transaction_id)
        with FileLock(self.lock):
            self.state();path=folder/"transaction.json";journal=read_json(path)
            if journal["status"] not in {"applying","recovery_required"}:return {"status":journal["status"],"no_op":True}
            if sha256(Path(journal["before_snapshot"]))!=journal["before_snapshot_sha256"]:raise StudioError(ErrorCode.SOURCE_CONFLICT,"Live recovery snapshot is corrupt")
            original=objects(journal["before"]);current=objects(self.backend.inspect());restored=[];conflicts=[]
            for record in journal["applied_objects"]:
                key=(record["slide_id"],record["object_id"]);own=record["state"]
                if key not in current or current[key]["fingerprint"]!=own["fingerprint"]:
                    conflicts.append(key);continue
                prior=original[key];operation=next(row for row in journal["patch"]["operations"] if (row["slide_id"],row["object_id"])==key)
                self.backend.restore(key[0],key[1],prior,current[key]["fingerprint"]);restored.append(key);current=objects(self.backend.inspect())
            if journal.get("pending_operation"):
                pending=journal["pending_operation"];key=(pending["slide_id"],pending["object_id"])
                if key not in original or key not in current or current[key]["fingerprint"]!=original[key]["fingerprint"]:conflicts.append(key)
            journal.update(status="recovered" if not conflicts else "recovery_conflict",restored=restored,conflicts=conflicts)
            write_json(path,journal)
            return {"status":journal["status"],"restored":restored,"conflicts":conflicts,"snapshot":journal["before_snapshot"],"user_edits_preserved":True}

    def save(self,policy,copy_path=None):
        with FileLock(self.lock):
            if policy!="manual":self._require_resolved_transactions()
            state=self.state();result=self.backend.save(policy,copy_path=copy_path)
            state["target_disk_fingerprint"]=getattr(self.backend,"disk_fingerprint",None)
            result["autosave_restored"]=self.backend.restore_autosave(state.get("autosave_policy",{}))
            state["history"].append({"event":"explicit_save","policy":policy,"at":now()});write_json(self.path,state)
            return result

    def detach(self):
        with FileLock(self.lock),self.project._lock():
            self._require_resolved_transactions()
            session=self.state();live=self.backend.inspect()
            target=Path(getattr(self.backend,"local_target",self.backend.target))
            if native_path(target)==native_path(self.project.canonical) and not live["saved"]:raise StudioError(ErrorCode.USER_ACTION_REQUIRED,"Save or close the unsaved canonical presentation before releasing live authority")
            state=self.project.state();state["authority"]="file"
            if native_path(target)==native_path(self.project.canonical):
                from presentation.live.disk import disk_fingerprint
                state["canonical_fingerprint"]=disk_fingerprint(self.project.canonical);state["generation"]+=1
            elif fingerprint(self.project.canonical)!=session["base_disk"]:raise StudioError(ErrorCode.FILE_CONFLICT,"Canonical disk changed during live session")
            session["status"]="detached";session["history"].append({"event":"detached","at":now()});write_json(self.path,session);write_yaml(self.project.state_path,state)
            self.backend.release();return {"passed":True,"user_presentation_closed":False,"unsaved_preserved":not live["saved"]}
