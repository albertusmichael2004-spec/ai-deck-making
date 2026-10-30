"""Explicit file-backed control adapter for live transaction guards, not native proof."""
from copy import deepcopy
import shutil
from uuid import uuid4

from presentation.backends.ooxml import OOXMLBackend
from presentation.live.inspection import digest
from state.io import fingerprint


class Backend:
    def __init__(self,root,project,source,renderer):
        self.root,self.project,self.source,self.renderer=root,project,source,renderer
        self.target,self.local_target=str(source),str(source);self.disk_fingerprint=fingerprint(source)
        self.files=OOXMLBackend(root);self.saved=True;self.snapshots={};self.hook=None;self.autosave=False

    def inspect(self):
        result=self.files.inspect(self.source)
        for slide in result["slides"]:
            for obj in slide["objects"]:
                obj["native_id"]=int(obj["native_id"])
                for key,value in obj["geometry"].items():obj[{"x":"x_pt","y":"y_pt","width":"width_pt","height":"height_pt"}[key]]=value*72
        return {**result,"canvas_pt":{"width":result["canvas"]["width_in"]*72,"height":result["canvas"]["height_in"]*72},"fingerprint":digest(result["slides"]),"full_name":self.target,"name":self.source.name,"saved":self.saved}

    def snapshot(self):
        path=self.project.path/"work"/("snapshot_"+uuid4().hex+".pptx");shutil.copy2(self.source,path)
        self.snapshots.update({obj["fingerprint"]:(path,slide["slide_id"],obj["object_id"]) for slide in self.inspect()["slides"] for obj in slide["objects"]})
        return {"path":str(path)}

    def render(self,source,output):return self.renderer.render(source,output)
    def pause_autosave(self):return {"available":True,"initial":False,"paused":False}
    def restore_autosave(self,policy):return False
    def save(self,policy,copy_path=None):return {"saved":False,"policy":policy,"unsaved_preserved":True}
    def release(self):pass

    def apply(self,operation,text_scope=None):
        if text_scope:
            from presentation.live.session import replace_range
            obj=next(o for s in self.inspect()["slides"] if s["slide_id"]==operation["slide_id"] for o in s["objects"] if o["object_id"]==operation["object_id"])
            operation={**operation,"value":replace_range(obj["text"],text_scope,operation["value"])}
        temporary=self.project.path/"work"/(uuid4().hex+".pptx")
        scope={"objects":[{"slide_id":operation["slide_id"],"object_id":operation["object_id"],"protection":"MAY_CHANGE"}]}
        self.files.patch(self.source,temporary,{"schema_version":"1.0","patch_id":"control","operations":[operation]},scope)
        shutil.copy2(temporary,self.source);self.saved=False
        if self.hook:self.hook(self)
        return self.inspect()

    def restore(self,sid,oid,prior,expected_fingerprint):
        from lxml import etree as ET
        from presentation.backends.xml import serialize
        from state.errors import StudioError,ErrorCode
        current=next(o for s in self.inspect()["slides"] if s["slide_id"]==sid for o in s["objects"] if o["object_id"]==oid)
        if current["fingerprint"]!=expected_fingerprint:raise StudioError(ErrorCode.LIVE_SELECTION_STALE,"Control recovery target changed")
        old_path,_,_=self.snapshots[prior["fingerprint"]]
        original=self.files._read(old_path);package=self.files._read(self.source)
        old_slide=next(node for identity,name,node in self.files._slide_entries(original)[1] if identity==sid)
        new_name,new_slide=next((name,node) for identity,name,node in self.files._slide_entries(package)[1] if identity==sid)
        old_shape=next(shape for identity,shape,props in self.files._objects(old_slide) if identity==oid)
        new_shape=next(shape for identity,shape,props in self.files._objects(new_slide) if identity==oid)
        new_shape.getparent().replace(new_shape,deepcopy(old_shape));package[new_name]=(package[new_name][0],serialize(new_slide))
        self.files._write(package,self.source);return self.inspect()
