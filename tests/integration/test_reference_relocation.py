from pathlib import Path
import shutil

import pytest

from references.catalog import DatabaseIntake, ReferenceCatalog
from references.migration import relocate_database
from references.store import ReferenceStore
from state.errors import StudioError
from state.io import native_path, read_json, write_json
from test_reference_scopes import deck, FixtureRenderer


def relocated(repo):
    catalog=ReferenceCatalog(repo,renderer=FixtureRenderer(repo))
    catalog.import_paths([deck(repo)])
    assert catalog.store('database').ingest()['passed']
    destination=repo.parent/(repo.name+'_renamed')
    shutil.copytree(native_path(repo),native_path(destination))
    return destination


def test_relocation_preserves_identity_provenance_and_loads(repo):
    destination=relocated(repo)
    before=DatabaseIntake(repo).state()
    with pytest.raises(StudioError):ReferenceStore(destination).state()
    report=relocate_database(destination,repo)
    assert report['status']=='complete'
    assert DatabaseIntake(destination).files()[0]['verified']
    assert DatabaseIntake(destination).state()['imports'][0]['original_path']==before['imports'][0]['original_path']
    store=ReferenceStore(destination)
    for key,record in store.state()['decks'].items():
        assert key in ReferenceStore(repo).state()['decks']
        for slide in record['slides']:
            for kind in ['preview','metadata','structure','original']:
                assert store.load(key,slide['slide_id'],kind)
    assert store.ingest(dry_run=True)['counts']=={'unchanged_skipped':1}


def test_relocation_rejects_modified_copy_before_publication(repo):
    destination=relocated(repo);store=ReferenceStore(destination)
    before=store.manifest.read_bytes()
    record=next(iter(read_json(store.manifest)['decks'].values()))['slides'][0]['artifacts']['preview']
    relative=Path(record['path']).relative_to(repo)
    native_path(destination/relative).write_bytes(b'changed')
    with pytest.raises(StudioError):relocate_database(destination,repo)
    assert store.manifest.read_bytes()==before


def test_relocation_rejects_unrelated_manifest_path(repo):
    destination=relocated(repo);store=ReferenceStore(destination)
    value=read_json(store.manifest)
    next(iter(value['decks'].values()))['snapshot']=str(repo.parent/'private/deck.pptx')
    write_json(store.manifest,value);before=store.manifest.read_bytes()
    with pytest.raises(StudioError):relocate_database(destination,repo)
    assert store.manifest.read_bytes()==before
