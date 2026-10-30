"""General Database plus one explicitly selected project's references."""
from pathlib import Path

from references.store import ReferenceStore
from state.errors import ErrorCode, StudioError
from state.intake import ProjectIntake, prepare_imports
from state.io import logical_path, native_path, read_json, sha256, write_json
from state.locking import FileLock
from state.workspace import Workspaces, now
from ir.validation import validate


class DatabaseIntake:
    def __init__(self, repository):
        self.root=repository.resolve();self.store=ReferenceStore(self.root)
        self.base=self.store.library_base("database")
        self.destination=self.store.policy.check(self.base/"originals",write=True)
        if logical_path(self.destination)!=logical_path(self.base/"originals"):
            raise StudioError(ErrorCode.SECURITY_BLOCK,"Database originals cannot be redirected")
        self.inventory=self.store.base/"manifests/imports.json"

    def state(self):
        value=read_json(self.inventory) if self.inventory.exists() else {"schema_version":"1.0","imports":[]}
        validate(self.root,"reference_imports",value)
        return value

    def import_paths(self, sources):
        prepared,registry,batch=prepare_imports(self.root,native_path(self.store.base),self.destination,sources,"reference")
        result=[]
        with FileLock(self.store.policy.check(self.store.lock,write=True)):
            value=self.state();known={(row["path"],row["original_path"]) for row in value["imports"]}
            for path,relative,expected in prepared:
                destination=self.destination/"uploads"/batch/relative
                if destination.exists():
                    if sha256(destination)!=expected["sha256"]:raise StudioError(ErrorCode.SOURCE_CONFLICT,"Database imported original has changed")
                elif registry.materialize(path,destination,"reference")["sha256"]!=expected["sha256"]:
                    raise StudioError(ErrorCode.SOURCE_CONFLICT,"Selected reference changed during import")
                row={"role":"reference","original_path":str(logical_path(path)),"path":str(logical_path(destination)),"relative_path":destination.relative_to(native_path(self.store.base)).as_posix(),"sha256":expected["sha256"],"bytes":expected["bytes"],"imported_at":now()}
                if (row["path"],row["original_path"]) not in known:
                    value["imports"].append(row);known.add((row["path"],row["original_path"]))
                result.append(row)
            validate(self.root,"reference_imports",value)
            write_json(self.store.policy.check(self.inventory,write=True),value)
        return result

    def files(self):
        result=[]
        for row in self.state()["imports"]:
            path=self.store.storage_path(Path(row["path"]))
            if not path.is_relative_to(self.destination) or path.relative_to(native_path(self.store.base)).as_posix()!=row["relative_path"]:
                raise StudioError(ErrorCode.SECURITY_BLOCK,"Database inventory points outside originals")
            result.append({**row,"verified":path.is_file() and sha256(path)==row["sha256"]})
        return result


class ReferenceCatalog:
    def __init__(self, repository, *, project_id=None, renderer=None, preferences=None):
        self.root=repository.resolve();self.project_id=project_id
        self.stores={"database":ReferenceStore(self.root,renderer,preferences)}
        if project_id is not None:
            # No active-project/cwd inference: authorization comes from the caller.
            self.stores["project"]=ReferenceStore(self.root,renderer,project_id=project_id)

    def store(self,scope):
        if scope not in self.stores:
            raise StudioError(ErrorCode.SECURITY_BLOCK,"Project references require --project at the beginning of this task")
        return self.stores[scope]

    def query(self,query,limit=8):
        rows=[{**row,"scope":scope,"project_id":self.project_id if scope=="project" else None} for scope,store in self.stores.items() for row in store.query(query,limit)]
        return sorted(rows,key=lambda row:(-row["score"],row["scope"],row["reference_id"],row["slide_id"]))[:limit]

    def load(self,reference_id,slide_id,stage="metadata",*,scope="database"):
        return {**self.store(scope).load(reference_id,slide_id,stage),"scope":scope,"project_id":self.project_id if scope=="project" else None}

    def files(self):
        rows=[{**row,"scope":"database","project_id":None} for row in DatabaseIntake(self.root).files()]
        if self.project_id:
            workspaces=Workspaces(self.root);project=workspaces.selected(self.project_id)
            rows.extend({**row,"scope":"project","project_id":self.project_id} for row in ProjectIntake(workspaces,project).files() if row["role"]=="reference")
        return rows

    def import_paths(self,sources,*,scope="database"):
        self.store(scope)
        if scope=="database":return DatabaseIntake(self.root).import_paths(sources)
        workspaces=Workspaces(self.root)
        return ProjectIntake(workspaces,workspaces.selected(self.project_id)).import_paths(sources,"reference")
