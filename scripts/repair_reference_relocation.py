"""Repair this workspace's verified general Database relocation with an audit."""
from pathlib import Path
import json
from references.migration import relocate_database
from references.catalog import DatabaseIntake
from references.store import ReferenceStore
from state.io import write_json

root=Path(__file__).resolve().parents[1]
report=relocate_database(root,root.parent/'Agent for Deck Making')
store=ReferenceStore(root)
report['dry_run']=store.ingest(dry_run=True)
report['registered_imports']=len(DatabaseIntake(root).files())
write_json(root/'implementation/PHASE_REPORTS/reference_relocation.json',report)
print(json.dumps({'status':report['status'],'backup':report['backup'],'verified_decks':report['verified_decks'],'registered_imports':report['registered_imports'],'dry_run':report['dry_run']},indent=2))
