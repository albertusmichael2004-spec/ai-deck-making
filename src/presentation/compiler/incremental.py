"""Recompile affected slides and import only their new dependency closures."""
import hashlib
import posixpath
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from evidence.dependencies import DependencyGraph
from ir.validation import validate
from presentation.backends.xml import NS,parse,serialize
from qa.regression import protected_scope
from state.errors import StudioError,ErrorCode
from state.io import write_json


def affected_slides(spec,graph,evidence_ids):
    dependencies=DependencyGraph(deepcopy(graph.value["dependencies"]))
    for slide in spec["slides"]:
        binding=graph.value["bindings"].get(slide["exhibit"].get("binding_id"),{})
        dependencies.register("slide:"+slide["slide_id"],[*slide["claim_ids"],*binding.get("evidence_ids",[])])
    affected=dependencies.affected(evidence_ids)
    return [slide["slide_id"] for slide in spec["slides"] if "slide:"+slide["slide_id"] in affected]


class IncrementalCompiler:
    def __init__(self,repository,compiler):self.root,self.compiler=repository,compiler

    def compile(self,source,destination,previous,revised,evidence,changed_evidence_ids,scope):
        backend=self.compiler.backend;before=backend.inspect(source)
        structural=lambda deck:{key:value for key,value in deck.items() if key not in {"core_answer","storyline"}}
        if previous["brief"]!=revised["brief"] or structural(previous["deck"])!=structural(revised["deck"]):raise StudioError(ErrorCode.SECURITY_BLOCK,"Incremental refresh cannot silently change the brief/deck structural contract")
        ids=set(affected_slides(revised,evidence.graph,changed_evidence_ids))
        old={s["slide_id"]:s for s in previous["slides"]}
        ids.update(s["slide_id"] for s in revised["slides"] if s!=old[s["slide_id"]])
        if not ids:
            import shutil
            shutil.copy2(source,destination)
            return {"passed":True,"no_op":True,"recompiled_slides":[]}
        stale=[]
        for slide in revised["slides"]:
            if slide["slide_id"] in ids:
                stale.extend(key for key in slide["claim_ids"] if evidence.graph.resolve(key)["status"]!="current")
        if stale:raise StudioError(ErrorCode.RESEARCH_INCOMPLETE,"Analytical refresh invalidated claims; regenerate and validate the storyline before exhibit compilation",stale_claim_ids=stale)
        # Prepare only affected layouts; full native post-repair rendering remains the regression gate.
        validate(self.root,"brief_spec",revised["brief"]);validate(self.root,"deck_spec",revised["deck"])
        compiled=[]
        for slide in revised["slides"]:
            if slide["slide_id"] not in ids:continue
            validate(self.root,"slide_spec",slide)
            notes=evidence.validate_slide(slide,revised["brief"]["constraints"]["sources_required"])
            prepared=deepcopy(slide)
            if slide["exhibit"]["type"] not in {"text","shapes","timeline","roadmap","issue_tree","scenario","recommendation"}:prepared["exhibit"]=evidence.resolve_exhibit(slide)
            layout=self.compiler.layout.compile(revised["deck"],prepared,source_notes=notes)
            for obj in layout["objects"]:validate(self.root,"object_spec",obj)
            compiled.append(layout)
        temporary=destination.with_name("incremental_"+uuid4().hex+".pptx")
        backend.create(compiled,revised["deck"]["canvas"],temporary,template=revised["deck"].get("template"))
        package=backend._read(source);generated=backend._read(temporary)
        _,existing=backend._slide_entries(package);_,new=backend._slide_entries(generated)
        original_map={sid:name for sid,name,_ in existing}
        token=uuid4().hex;mapping={name:original_map[sid] for sid,name,_ in new}
        reusable={name for name in generated if name.startswith(("ppt/slideMasters/","ppt/slideLayouts/","ppt/theme/")) and name in package and generated[name][1]==package[name][1]}
        mapping.update({name:name for name in reusable})
        content_types=parse(package["[Content_Types].xml"][1]);generated_types=parse(generated["[Content_Types].xml"][1])
        imported=set()
        def import_part(name):
            if name in reusable:return name
            if name.startswith("ppt/slideMasters/") and not name.endswith(".rels"):raise StudioError(ErrorCode.SECURITY_BLOCK,"Incremental refresh requires the original registered master; restyling needs explicit whole-deck scope")
            if name not in mapping:
                parent,filename=posixpath.split(name);mapping[name]=posixpath.join(parent,"studio_"+token+"_"+filename)
            target=mapping[name]
            if name in imported:return target
            imported.add(name);package[target]=(None,generated[name][1])
            rel_name=posixpath.join(posixpath.dirname(name),"_rels",posixpath.basename(name)+".rels")
            if rel_name in generated:
                relations=parse(generated[rel_name][1])
                for relation in relations:
                    if relation.get("TargetMode")=="External":continue
                    dependency=posixpath.normpath(posixpath.join(posixpath.dirname(name),relation.get("Target")))
                    if dependency not in generated:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Unresolved incremental dependency")
                    new_target=import_part(dependency)
                    relation.set("Target",posixpath.relpath(new_target,posixpath.dirname(target)))
                out_rel=posixpath.join(posixpath.dirname(target),"_rels",posixpath.basename(target)+".rels")
                package[out_rel]=(None,serialize(relations))
            for item in generated_types:
                if item.tag.endswith("Override") and item.get("PartName")=="/"+name and not any(row.get("PartName")=="/"+target for row in content_types):
                    copied=deepcopy(item);copied.set("PartName","/"+target);content_types.append(copied)
                elif item.tag.endswith("Default") and not any(row.get("Extension")==item.get("Extension") for row in content_types):content_types.append(deepcopy(item))
            return target
        for _,name,_ in new:import_part(name)
        package["[Content_Types].xml"]=(package["[Content_Types].xml"][0],serialize(content_types))
        # Existing masters/layouts/media/workbooks are retained byte-for-byte; dependency imports use new names.
        backend._write(package,destination)
        after=backend.inspect(destination)
        if not protected_scope(before,after,scope)["passed"]:raise StudioError(ErrorCode.SECURITY_BLOCK,"Incremental compilation would change protected objects")
        evidence.assert_current()
        result={"passed":True,"no_op":False,"recompiled_slides":sorted(ids),"imported_parts":sorted(mapping.values())}
        write_json(destination.with_suffix(".incremental.json"),result)
        return result
