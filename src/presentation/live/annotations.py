"""Resolve scoped comment targets conservatively; keep immutable comment provenance."""
import math
import re
from copy import deepcopy

from preferences.classification import classify
from presentation.live.inspection import digest,now
from state.errors import StudioError,ErrorCode
from state.io import read_json,write_json
from state.locking import FileLock


UNSAFE=re.compile(r"ignore (all|previous)|disable (security|qa|critic)|execute (code|shell|python|commands)|powershell|cmd /|delete files|upload|api[_ -]?key|password|system prompt|network permissions",re.I)


class AnnotationResolver:
    def __init__(self,threshold=.8,margin=.15):self.threshold,self.margin=threshold,margin

    def resolve(self,comment,inspection,scope,*,selection=None):
        row={**deepcopy(comment),"schema_version":"1.0","resolved_target_ids":[],"resolution_confidence":0,"intent_class":classify(comment["text"])["type"],"constraints":["terminal_scope","protected_objects","preserve_original_comment"],"status":"discovered"}
        if UNSAFE.search(row["text"]):return {**row,"status":"blocked","reason":"Comment attempted to change runtime/security policy"}
        slide=next((s for s in inspection["slides"] if s["slide_id"]==row["slide_id"]),None)
        if slide is None:return {**row,"status":"blocked","reason":"Comment slide is missing"}
        allowed={(o["slide_id"],o["object_id"]) for o in scope["objects"] if o["protection"]!="MUST_NOT_CHANGE"}
        text=row["text"].lower();candidates=[]
        for obj in slide["objects"]:
            if (slide["slide_id"],obj["object_id"]) not in allowed:continue
            x,y,w,h=(obj[key] for key in ["x_pt","y_pt","width_pt","height_pt"])
            anchor=row.get("anchor") or {};px,py=anchor.get("left_pt"),anchor.get("top_pt")
            inside=px is not None and py is not None and x<=px<=x+w and y<=py<=y+h
            distance=math.hypot(max(x-px,0,px-x-w),max(y-py,0,py-y-h)) if px is not None and py is not None else 1000
            score=.65 if inside else max(0,.4*(1-distance/72))
            kind="chart" if "chart_series" in obj else "table" if "table_cells" in obj else "title" if obj.get("role")=="title" or "title" in obj.get("name","").lower() else "text" if obj.get("text") else "shape"
            if kind in text:score+=.25
            tokens=set(re.findall(r"[a-z]{3,}",obj.get("text","").lower()))
            overlap=len(tokens&set(re.findall(r"[a-z]{3,}",text)))
            if overlap:score+=min(.2,.05*overlap)
            if selection and any(r["object_id"]==obj["object_id"] and r["slide_id"]==slide["slide_id"] for r in selection["objects"]):score+=.2
            candidates.append((min(1,score),obj["object_id"]))
        candidates.sort(reverse=True)
        if candidates and candidates[0][0]>=self.threshold and (len(candidates)==1 or candidates[0][0]-candidates[1][0]>=self.margin):
            row.update(status="planned",resolved_target_ids=[candidates[0][1]],resolution_confidence=round(candidates[0][0],4))
        elif re.search(r"\b(whole|entire|overall) slide\b",text) and all((slide["slide_id"],obj["object_id"]) in allowed for obj in slide["objects"]):
            row.update(status="planned",resolved_target_ids=[obj["object_id"] for obj in slide["objects"]],resolution_confidence=.85)
        else:row.update(status="ambiguous",reason="Insufficient target confidence or conflicting nearby targets",candidates=[{"object_id":key,"score":score} for score,key in candidates[:5]])
        return row


class CommentLedger:
    def __init__(self,project):
        self.project=project;self.path=project.path/"state/comment_ledger.json";self.lock=project.path/"work/comment_ledger.lock"

    def load(self):return read_json(self.path) if self.path.exists() else {"schema_version":"1.0","comments":{}}

    def scan(self,rows,*,authors=(),slide_ids=(),include_processed=False):
        with FileLock(self.lock):
            state=self.load();result=[]
            for row in rows:
                if authors and row["author"] not in authors or slide_ids and row["slide_id"] not in slide_ids:continue
                key=row["annotation_id"]
                prior=state["comments"].get(key)
                if prior and {key:value for key,value in prior["comment"].items() if key!="replies"}!={key:value for key,value in row.items() if key!="replies"}:raise StudioError(ErrorCode.FILE_CONFLICT,"Stable comment identity collided with different content")
                if prior:prior["comment"]["replies"]=deepcopy(row.get("replies",[]))
                if prior is None:
                    prior={"comment":deepcopy(row),"status":"discovered","history":[{"status":"discovered","at":now()}]};state["comments"][key]=prior
                if include_processed or prior["status"] not in {"applied","ignored"}:result.append(deepcopy(prior))
            write_json(self.path,state);return result

    def mark(self,annotation_id,status,*,transaction_id=None,resolution=None):
        if status not in {"discovered","planned","applied","blocked","ambiguous","ignored"}:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Invalid comment ledger status")
        with FileLock(self.lock):
            state=self.load()
            if annotation_id not in state["comments"]:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Comment is not registered")
            row=state["comments"][annotation_id]
            if row["status"]==status and row.get("transaction_id")==transaction_id:return row
            row.update(status=status,transaction_id=transaction_id)
            if resolution is not None:row["resolution"]=deepcopy(resolution)
            row["history"].append({"status":status,"at":now(),"transaction_id":transaction_id});write_json(self.path,state)
            return row
