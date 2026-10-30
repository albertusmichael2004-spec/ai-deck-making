"""Audited, resumable consolidation of unindexed legacy original collections."""
from pathlib import Path

from references.catalog import DatabaseIntake
from state.errors import ErrorCode, StudioError
from state.io import logical_path, native_path, read_json, sha256, write_json
from state.locking import FileLock
from state.workspace import now


def relocate_database(repository, previous_root):
    """Rebind general Database storage after an explicit workspace relocation.

    Never read the old root or infer authority from stored manifest paths.
    Current scoped copies must match every recorded hash before publication.
    External input provenance and past migration audits remain unchanged.
    """
    from copy import deepcopy
    from uuid import uuid4
    from ir.validation import validate

    intake=DatabaseIntake(repository);store=intake.store
    old_base=logical_path(Path(previous_root).resolve())/"library/references"
    current_base=logical_path(store.base)
    if old_base==current_base:
        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Previous and current reference roots are identical")
    with FileLock(store.policy.check(store.lock,write=True)):
        state=read_json(store.manifest);inventory=intake.state()
        changes=[]

        def rebind(value, expected=None):
            path=logical_path(Path(value))
            if path.is_relative_to(old_base):
                target=store.storage_path(current_base/path.relative_to(old_base))
            elif path.is_relative_to(current_base):
                target=store.storage_path(path)
            else:
                raise StudioError(ErrorCode.SECURITY_BLOCK,"Relocation path is outside the explicitly selected Database roots")
            if expected and (not target.is_file() or sha256(target)!=expected):
                raise StudioError(ErrorCode.SOURCE_CONFLICT,"Relocated reference file is missing or changed")
            rebound=str(logical_path(target))
            if rebound!=value:changes.append({"before":value,"after":rebound})
            return rebound

        candidate=deepcopy(state);imports=deepcopy(inventory)
        for deck in candidate["decks"].values():
            for version in [deck,*deck.get("history",[])]:
                version["snapshot"]=rebind(version["snapshot"],version["file_sha256"])
            deck["source_path"]=rebind(deck["source_path"],deck["file_sha256"])
            for slide in deck["slides"]:
                for record in slide["artifacts"].values():record["path"]=rebind(record["path"],record["sha256"])
                if slide.get("promoted_original"):slide["promoted_original"]=rebind(slide["promoted_original"],deck["file_sha256"])
        candidate["aliases"]={rebind(path):value for path,value in candidate["aliases"].items()}
        if "excluded_sources" in candidate:candidate["excluded_sources"]=[rebind(path) for path in candidate["excluded_sources"]]
        for row in imports["imports"]:
            row["path"]=rebind(row["path"],row["sha256"])
            target=store.storage_path(Path(row["path"]))
            if not target.is_relative_to(intake.destination) or target.relative_to(native_path(store.base)).as_posix()!=row["relative_path"]:
                raise StudioError(ErrorCode.SECURITY_BLOCK,"Relocated inventory escaped Database originals")
        validate(store.root,"reference_manifest",candidate)
        validate(store.root,"reference_imports",imports)
        backup=store.root/"runtime/reference_ingestion"/("relocation_"+uuid4().hex)
        backup=store.policy.check(backup,write=True)
        write_json(backup/"library.before.json",state)
        write_json(backup/"imports.before.json",inventory)
        if store.index.exists():write_json(backup/"index.before.json",read_json(store.index))
        report={"schema_version":"1.0","time":now(),"previous_root":str(previous_root),"current_root":str(store.root),"changes":changes,"backup":str(logical_path(backup)),"verified_decks":len(candidate["decks"]),"verified_imports":len(imports["imports"])}
        write_json(backup/"plan.json",report)
        write_json(store.policy.check(intake.inventory,write=True),imports)
        write_json(store.policy.check(store.manifest,write=True),candidate)
        store._write_index(candidate)
        store.state();intake.files()
        report["status"]="complete"
        write_json(backup/"result.json",report)
        return report


def consolidate_unindexed(repository):
    intake=DatabaseIntake(repository);store=intake.store
    audit=store.base/"manifests/database_migration.json"
    with FileLock(store.policy.check(store.lock,write=True)):
        state=store.state()
        if state["decks"] or state["aliases"]:
            if audit.exists():
                completed=read_json(store.storage_path(audit))
                if completed.get("status")=="complete":
                    for row in completed["rows"]:
                        path=store.storage_path(Path(row["destination"]))
                        if not path.is_file() or sha256(path)!=row["sha256"]:
                            raise StudioError(ErrorCode.SOURCE_CONFLICT,"Previously migrated original changed")
                    return completed
            raise StudioError(ErrorCode.USER_ACTION_REQUIRED,"Indexed legacy decks need a dedicated path/provenance migration; do not move their folders manually")
        if audit.exists():
            plan=read_json(store.storage_path(audit))
        else:
            rows=[];names=set()
            for library in ["approved_internal","external"]:
                base=store.library_base(library)
                if not base.exists():continue
                if logical_path(native_path(base/"originals"))!=logical_path(base/"originals"):
                    raise StudioError(ErrorCode.SECURITY_BLOCK,"Legacy originals cannot be redirected")
                if any(path.is_file() for folder in ["metadata","previews"] for path in (base/folder).rglob("*")):
                    raise StudioError(ErrorCode.FILE_CONFLICT,"Unregistered legacy derivatives need review before consolidation")
                for source in sorted((base/"originals").rglob("*")):
                    if source.is_symlink() or source.is_junction():
                        raise StudioError(ErrorCode.SECURITY_BLOCK,"Legacy reference folders cannot contain links")
                    if not source.is_file():continue
                    relative=source.relative_to(base/"originals")
                    destination=intake.destination/relative
                    name=relative.as_posix().casefold()
                    if name in names or destination.exists():
                        raise StudioError(ErrorCode.FILE_CONFLICT,"Legacy original filenames collide; review before migration")
                    names.add(name)
                    rows.append({"source":str(logical_path(source)),"destination":str(logical_path(destination)),"sha256":sha256(source),"bytes":source.stat().st_size,"legacy_library":library})
            plan={"schema_version":"1.0","status":"planned","created_at":now(),"rows":rows,"excluded_sources_before":state.get("excluded_sources",[])}
            write_json(store.policy.check(audit,write=True),plan)
        inventory=intake.state();known={row["path"] for row in inventory["imports"]};exclusions=[]
        for row in plan["rows"]:
            source=store.storage_path(Path(row["source"]));destination=store.policy.check(Path(row["destination"]),write=True)
            expected=store.library_base(row["legacy_library"])/"originals"
            if not source.is_relative_to(native_path(expected)) or not destination.is_relative_to(intake.destination):
                raise StudioError(ErrorCode.SECURITY_BLOCK,"Migration path escaped original collections")
            if source.exists():
                if sha256(source)!=row["sha256"] or destination.exists():
                    raise StudioError(ErrorCode.FILE_CONFLICT,"Migration original changed or destination appeared")
                destination.parent.mkdir(parents=True,exist_ok=True)
                source.rename(destination)
            if not destination.is_file() or sha256(destination)!=row["sha256"]:
                raise StudioError(ErrorCode.SOURCE_CONFLICT,"Migrated original hash differs")
            if row["source"] in plan["excluded_sources_before"]:
                exclusions.append(row["destination"])
            elif not destination.name.endswith(".source.json") and row["destination"] not in known:
                inventory["imports"].append({"role":"reference","original_path":row["source"],"path":row["destination"],"relative_path":destination.relative_to(native_path(store.base)).as_posix(),"sha256":row["sha256"],"bytes":row["bytes"],"imported_at":plan["created_at"]})
                known.add(row["destination"])
        state.update(schema_version="1.1",excluded_sources=sorted(set([*exclusions,*plan["excluded_sources_before"]])))
        write_json(store.policy.check(store.manifest,write=True),state);store._write_index(state)
        write_json(store.policy.check(intake.inventory,write=True),inventory)
        # Only remove verified empty legacy directories, never recursive deletion.
        for library in ["approved_internal","external"]:
            base=store.library_base(library)
            if base.exists():
                for folder in sorted([path for path in base.rglob("*") if path.is_dir()],key=lambda path:len(path.parts),reverse=True):
                    if not any(folder.iterdir()):store.storage_path(folder).rmdir()
                if not any(base.iterdir()):store.storage_path(base).rmdir()
        plan.update(status="complete",verified_at=now(),moved_files=len(plan["rows"]),registered_files=len(inventory["imports"]))
        write_json(store.policy.check(audit,write=True),plan)
        return plan
