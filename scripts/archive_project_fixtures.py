"""Archive verified synthetic project trees before the operator's cleanup."""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from state.io import read_json,read_yaml,write_json,native_path,logical_path,open_read,sha256
from state.workspace import FIXTURE

plan=read_json(ROOT/'implementation/PHASE_REPORTS/workspace_cleanup_plan_20261024.json')
assert Path(plan['root']).resolve()==ROOT
archive_path=ROOT/'implementation/ARCHIVES/project_fixtures_20261024.zip'
archive_path.parent.mkdir(exist_ok=True)
records=[];empty_dirs=[]
def walk(folder):
    pending=[native_path(folder)]
    while pending:
        directory=pending.pop()
        entries=list(os.scandir(directory))
        if not entries:empty_dirs.append(logical_path(Path(directory)).relative_to(ROOT).as_posix()+'/')
        for entry in entries:
            info=entry.stat(follow_symlinks=False)
            if entry.is_symlink() or getattr(info,'st_reparse_tag',0) in {0xA0000003,0xA000000C}:
                raise RuntimeError('Fixture contains a filesystem link: '+entry.path)
            if entry.is_dir(follow_symlinks=False):pending.append(Path(entry.path))
            else:yield Path(entry.path),info

with zipfile.ZipFile(native_path(archive_path),'x',zipfile.ZIP_DEFLATED,compresslevel=3,allowZip64=True) as archive:
    for index,name in enumerate(plan['fixtures']):
        assert FIXTURE.fullmatch(name)
        folder=ROOT/'projects'/name
        assert not folder.is_symlink() and not folder.is_junction()
        assert not (folder/'state/workspace.json').exists()
        assert read_yaml(folder/'project.yaml')['project_id']==name
        for path,before in walk(folder):
            relative=logical_path(path).relative_to(ROOT).as_posix()
            digest=hashlib.sha256()
            info=zipfile.ZipInfo.from_file(path,relative,strict_timestamps=False)
            info.compress_type=zipfile.ZIP_DEFLATED
            with open_read(path) as incoming,archive.open(info,'w',force_zip64=True) as outgoing:
                while data:=incoming.read(1024*1024):digest.update(data);outgoing.write(data)
            after=path.stat()
            assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns),relative
            records.append({'path':relative,'sha256':digest.hexdigest(),'bytes':after.st_size,'mtime_ns':after.st_mtime_ns})
        if (index+1)%8==0:print('Archived',index+1,'of',len(plan['fixtures']),flush=True)
    for directory in empty_dirs:archive.writestr(directory,b'')
    manifest={'schema_version':'1.0','original_root':str(ROOT),'created_at':datetime.now(timezone.utc).isoformat(),'fixtures':plan['fixtures'],'files':records,'empty_directories':empty_dirs,'restore_note':'Members retain original projects/ paths and provenance bytes; extract only when explicitly restoring historical validation evidence.'}
    archive.writestr('ARCHIVE_MANIFEST.json',json.dumps(manifest,indent=2))

with zipfile.ZipFile(native_path(archive_path)) as archive:
    for record in records:
        digest=hashlib.sha256()
        with archive.open(record['path']) as incoming:
            while data:=incoming.read(1024*1024):digest.update(data)
        assert digest.hexdigest()==record['sha256'],record['path']
        assert sha256(ROOT/record['path'])==record['sha256'],'Source changed: '+record['path']

result={'schema_version':'1.0','status':'archive_verified_ready_for_cleanup','archive':str(archive_path),'archive_sha256':sha256(archive_path),'fixture_count':len(plan['fixtures']),'file_count':len(records),'archived_bytes':sum(r['bytes'] for r in records),'fixtures':plan['fixtures'],'kept_projects':plan['keep'],'files':records,'pytest_target':str(ROOT/'runtime/pytest'),'deleted':False}
write_json(ROOT/'implementation/PHASE_REPORTS/workspace_cleanup_20261024.json',result)
print(json.dumps({key:value for key,value in result.items() if key not in {'files','fixtures'}},indent=2))
