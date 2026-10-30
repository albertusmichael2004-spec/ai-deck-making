"""Preserve early development references while excluding them from runtime retrieval."""
import re
import sys
from pathlib import Path

root=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(root/"src"),str(root/"runtime/python_packages")]
from references.store import ReferenceStore
from state.io import write_json

store=ReferenceStore(root);state=store.state();excluded=set(state.get("excluded_sources",[]))
for deck in state["decks"].values():
    if re.fullmatch(r"native-reference-[a-f0-9]{10}\.pptx",Path(deck["source_path"]).name):
        deck.update(active=False,purpose="development_evaluation_fixture")
        excluded.add(deck["source_path"])
state["excluded_sources"]=sorted(excluded)
if store.manifest.exists():
    write_json(store.policy.check(store.manifest,write=True),state);store._write_index(state)
print({"evaluation_sources_excluded":len(excluded),"originals_preserved":True})
