"""Idempotent feedback events; contextual preferences are rebuildable derivatives."""
import hashlib
import json
import math
from datetime import datetime,timezone,timedelta
from pathlib import Path
from uuid import uuid4

from evidence.store import identity
from preferences.classification import classify
from security.paths import PathPolicy
from state.errors import StudioError,ErrorCode
from state.io import read_json,read_yaml,write_json,sha256,native_path
from state.locking import FileLock
from ir.validation import validate


def canonical_context(context=None):
    if context is not None and not isinstance(context,dict):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Preference context must be an object")
    value={"user_id":"local","project_id":"*","brand":"*",**(context or {})}
    if set(value)!={"user_id","project_id","brand"} or any(not isinstance(item,str) or not item or len(item)>128 for item in value.values()):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Invalid preference context")
    return value


class PreferenceStore:
    def __init__(self,repository):
        self.root=repository;self.base=native_path(repository/"library/preferences")
        self.policy=PathPolicy([self.base],[self.base]);self.events=self.base/"feedback_events";self.state_path=self.base/"preference_state/state.json";self.rules_path=self.base/"user_rules/rules.json";self.lock=self.base/"preference_state/preference.lock"
        self.config=read_yaml(repository/"config/preferences/default.yaml")
        if any(type(self.config.get(key)) not in {int,float} or not math.isfinite(self.config[key]) or self.config[key]<=0 for key in ["prior_weight","half_life_days","implicit_strength","rerank_weight"]):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Invalid preference learning bounds")
        if self.config["implicit_strength"]>1 or self.config["rerank_weight"]>1:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Preference strengths must be bounded")
        if self.config["prior_weight"]<2 or self.config["implicit_strength"]>.25:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Single/implicit observations must remain modest")

    def record(self,text,pattern,*,context=None,event_id=None,declared_type=None,polarity=None,signal=None,dimensions=(),tags=(),occurred_at=None):
        if not isinstance(text,str) or len(text)>8192 or not isinstance(pattern,str) or not pattern or len(pattern)>256:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Invalid feedback content/pattern")
        context=canonical_context(context);classification=classify(text,declared_type=declared_type,polarity=polarity,signal=signal)
        event_id=event_id or uuid4().hex
        if not isinstance(event_id,str) or not event_id or len(event_id)>256:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Invalid feedback event identity")
        if not isinstance(dimensions,(list,tuple)) or not isinstance(tags,(list,tuple)):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Feedback tags/dimensions must be arrays")
        request={"text":text,"pattern":pattern,"context":context,"declared_type":declared_type,"polarity":polarity,"signal":signal,"dimensions":list(dimensions),"tags":list(tags),"occurred_at":occurred_at}
        if any(not isinstance(item,str) or len(item)>128 for item in [*request["dimensions"],*request["tags"]]):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Invalid feedback tags/dimensions")
        digest=hashlib.sha256(json.dumps(request,sort_keys=True,allow_nan=False).encode()).hexdigest();path=self.policy.check(self.events/(identity("event",event_id)+".json"),write=True)
        with FileLock(self.policy.check(self.lock,write=True)):
            if path.exists():
                event=read_json(path)
                if event["request_sha256"]!=digest:raise StudioError(ErrorCode.FILE_CONFLICT,"Feedback identity was reused with different content")
                self._rebuild();return {"status":"unchanged","event":event}
            now=datetime.now(timezone.utc)
            try:timestamp=datetime.fromisoformat(occurred_at) if occurred_at else now
            except (ValueError,TypeError) as exc:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Feedback date is invalid") from exc
            if timestamp.tzinfo is None or timestamp>now+timedelta(minutes=5):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Feedback date must be timezone-aware and cannot be in the future")
            timestamp=timestamp.astimezone(timezone.utc)
            event={"schema_version":"1.0","event_id":event_id,"request_sha256":digest,"text":text,"pattern":pattern,"context":context,**classification,"dimensions":request["dimensions"],"tags":request["tags"],"occurred_at":timestamp.isoformat(),"strength":self.config["implicit_strength"] if classification["implicit"] else 1.0}
            validate(self.root,"feedback_event",event)
            write_json(path,event);self._rebuild();return {"status":"recorded","event":event}

    def _rebuild(self):
        records={};hashes={};now=datetime.now(timezone.utc)
        for path in sorted(self.events.glob("*.json")):
            path=self.policy.check(path);event=read_json(path);hashes[path.name]=sha256(path)
            validate(self.root,"feedback_event",event)
            if not event["learnable"] or event["type"] not in {"DESIGN_FEEDBACK","COPY_PREFERENCE"} or event["polarity"]=="neutral":continue
            key=identity("preference",json.dumps([event["pattern"],event["context"]],sort_keys=True))
            if not classify(event["text"],declared_type=event["type"],polarity=event["polarity"],signal=event["signal"])["learnable"]:continue
            row=records.setdefault(key,{"pattern":event["pattern"],"context":event["context"],"weighted_signal":0.0,"weight":0.0,"sample_count":0,"tags":[],"dimensions":[],"deprecated":False,"last_observed_at":event["occurred_at"],"observations":[]})
            age=max(0,(now-datetime.fromisoformat(event["occurred_at"])).total_seconds()/86400)
            weight=event["strength"]*2**(-age/self.config["half_life_days"])
            row["weighted_signal"]+=weight*(1 if event["polarity"]=="positive" else -1);row["weight"]+=weight;row["sample_count"]+=1
            row["tags"]=sorted(set(row["tags"])|set(event["tags"]));row["dimensions"]=sorted(set(row["dimensions"])|set(event["dimensions"]));row["last_observed_at"]=max(row["last_observed_at"],event["occurred_at"])
            row["deprecated"]|=event["polarity"]=="deprecated"
            row["observations"].append({"occurred_at":event["occurred_at"],"weight":weight,"signal":weight*(1 if event["polarity"]=="positive" else -1),"deprecated":event["polarity"]=="deprecated"})
        for row in records.values():row["preference_score"]=round(row["weighted_signal"]/(self.config["prior_weight"]+row["weight"]),6)
        result={"schema_version":"1.0","rebuilt_at":now.isoformat(),"event_hashes":hashes,"records":records};write_json(self.policy.check(self.state_path,write=True),result);return result

    def state(self):
        with FileLock(self.policy.check(self.lock,write=True)):return self._rebuild()

    def score(self,pattern,context=None):
        context=canonical_context(context);state=self.state();rules=read_json(self.rules_path) if self.rules_path.exists() else {"overrides":[],"resets":[]}
        return self._score(pattern,context,state,rules)

    def _score(self,pattern,context,state,rules):
        def matches(saved):return saved["user_id"]==context["user_id"] and all(saved[key] in {"*",context[key]} for key in ["brand","project_id"])
        selected=[row for row in rules["overrides"] if row["pattern"]==pattern and matches(row["context"])]
        if selected:
            row=max(selected,key=lambda row:sum(value!="*" for value in row["context"].values()))
            return {"score":row["score"],"deprecated":row.get("deprecated",False),"sample_count":0,"override":True}
        cutoff=max((row["reset_at"] for row in rules["resets"] if row["pattern"]==pattern and matches(row["context"])),default="")
        rows=[row for row in state["records"].values() if row["pattern"]==pattern and matches(row["context"])]
        observations=[value for row in rows for value in row["observations"] if value["occurred_at"]>cutoff]
        weight=sum(row["weight"] for row in observations);signal=sum(row["signal"] for row in observations)
        return {"score":round(signal/(self.config["prior_weight"]+weight),6),"deprecated":any(row["deprecated"] for row in observations),"sample_count":len(observations),"override":False}

    def override(self,pattern,score,*,context=None,deprecated=False):
        if type(score) not in {int,float} or not math.isfinite(score) or not -1<=score<=1:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Preference override must be between -1 and 1")
        return self._rule(pattern,context,{"score":score,"deprecated":bool(deprecated)},False)

    def reset(self,pattern,*,context=None):return self._rule(pattern,context,{},True)

    def _rule(self,pattern,context,values,reset):
        if not isinstance(pattern,str) or not pattern or len(pattern)>256:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Preference rule requires a valid pattern")
        context=canonical_context(context)
        with FileLock(self.policy.check(self.lock,write=True)):
            rules=read_json(self.rules_path) if self.rules_path.exists() else {"schema_version":"1.0","overrides":[],"resets":[]}
            for kind in ["overrides","resets"]:rules[kind]=[row for row in rules[kind] if row["pattern"]!=pattern or row["context"]!=context]
            rules["resets" if reset else "overrides"].append({"pattern":pattern,"context":context,**values,**({"reset_at":datetime.now(timezone.utc).isoformat()} if reset else {})})
            write_json(self.policy.check(self.rules_path,write=True),rules)
            return {"status":"reset" if reset else "overridden","pattern":pattern,"context":context}

    def rerank(self,candidates,context=None):
        results=[];context=canonical_context(context);state=self.state();rules=read_json(self.rules_path) if self.rules_path.exists() else {"overrides":[],"resets":[]}
        for candidate in candidates:
            row=dict(candidate);preference=self._score(row["pattern"],context,state,rules)
            row["preference"]=preference;row["base_score"]=row["score"];row["score"]=round(row["score"]+self.config["rerank_weight"]*preference["score"]-(1 if preference["deprecated"] else 0),6);results.append(row)
        return sorted(results,key=lambda row:(-row["score"],row["pattern"]))
