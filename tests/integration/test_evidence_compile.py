import copy
from pathlib import Path

import pytest
from pptx import Presentation

from evidence.context import EvidenceContext
from evidence.store import EvidenceStore
from layout.baseline import BaselineLayout
from presentation.backends.ooxml import OOXMLBackend
from presentation.compiler.compiler import PresentationCompiler
from state.errors import StudioError
from state.io import read_json


def test_evidence_required_compilation_resolves_claims_and_editable_source_notes(repo,project):
    source=repo/"data.csv";source.write_text("profit\n40\n",encoding="utf-8")
    store=EvidenceStore(repo,project);record=store.ingest(source,units={"default":{"label":"currency","currency":"IDR"}},data_period="2025")
    graph=store.load();identifier=record["evidence_ids"][0]
    spec=read_json(Path(__file__).resolve().parents[1]/"fixtures/basic_spec.json")
    spec["brief"]["constraints"]["sources_required"]=True
    for slide in spec["slides"]:
        slide["claim_ids"]=[identifier];slide["source_note_ids"]=[record["source_id"]]
    compiler=PresentationCompiler(repo,BaselineLayout(repo),OOXMLBackend(repo))
    output=repo/"runtime/evidence.pptx"
    compiler.compile(spec["brief"],spec["deck"],spec["slides"],output,EvidenceContext(graph,project.policy))
    assert "Source: data.csv (2025)" in Presentation(output).slides[0].shapes[-1].text
    invalid=copy.deepcopy(spec);invalid["slides"][0]["source_note_ids"]=[]
    with pytest.raises(StudioError):compiler.compile(invalid["brief"],invalid["deck"],invalid["slides"],repo/"runtime/bad.pptx",EvidenceContext(graph,project.policy))
    graph.resolve(identifier)["value"]="999"
    with pytest.raises(StudioError):compiler.compile(spec["brief"],spec["deck"],spec["slides"],repo/"runtime/tampered.pptx",EvidenceContext(graph,project.policy))
