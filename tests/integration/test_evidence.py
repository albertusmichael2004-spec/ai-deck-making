from pathlib import Path
from decimal import Decimal

import pytest

from evidence.store import EvidenceStore
from evidence.extraction import extract
from evidence.calculation import calculate,verify_number
from evidence.dependencies import DependencyGraph
from evidence.verification import EvidenceVerifier
from state.errors import StudioError
from state.io import sha256


def test_csv_calculation_claim_lineage_binding_and_refresh(project,repo):
    source=repo/"sales.csv";source.write_text("region,revenue,cost\nJakarta,100,60\n",encoding="utf-8")
    store=EvidenceStore(repo,project)
    result=store.ingest(source,units={"revenue":{"label":"currency","currency":"IDR"},"cost":{"label":"currency","currency":"IDR"}},source_date="2026-01-01",data_period="2025")
    graph=store.load();nodes=[graph.resolve(i) for i in result["evidence_ids"]]
    revenue=next(n["evidence_id"] for n in nodes if n["locator"].endswith("column:revenue"));cost=next(n["evidence_id"] for n in nodes if n["locator"].endswith("column:cost"))
    graph.calculate("profit","revenue-cost",{"revenue":revenue,"cost":cost},{"label":"currency","currency":"IDR"})
    graph.register({"evidence_id":"claim-profit","type":"interpretation","text":"Supplied profit is positive","supported_by":["profit"]})
    graph.bind("binding-profit",["profit"],"s01","exhibit-profit")
    store.save(graph)
    assert graph.resolve("profit")["value"]=="40"
    verifier=EvidenceVerifier(project.policy)
    assert verifier.displayed(graph,"profit","40") and not verifier.displayed(graph,"profit","41")
    graph.resolve("profit")["value"]="999"
    with pytest.raises(StudioError):verifier.value(graph,"profit")
    graph.resolve("profit")["value"]="40"
    assert {n["evidence_id"] for n in graph.trace("claim-profit")}=={"claim-profit","profit",revenue,cost}
    original_copy=Path(graph.value["sources"][result["source_id"]]["materialized_path"])
    old_hash=sha256(original_copy)
    assert store.refresh(result["source_id"])["status"]=="unchanged"
    source.write_text("region,revenue,cost\nJakarta,120,60\n",encoding="utf-8")
    refreshed=store.refresh(result["source_id"]);graph=store.load()
    assert graph.resolve("profit")["value"]=="60"
    assert graph.resolve("claim-profit")["status"]=="stale"
    assert {"s01","exhibit-profit","binding-profit","claim-profit","profit"}<=set(refreshed["affected"])
    assert sha256(original_copy)==old_hash
    assert len(graph.value["sources"][result["source_id"]]["previous_versions"])==1
    gaps=graph.gaps([{"question_id":"profit-q","question":"Is profit positive?","evidence_ids":["claim-profit"]},{"question_id":"current-q","question":"Is revenue current?","evidence_ids":[revenue],"max_age_days":1}])
    assert len(gaps)==2


def test_removed_source_values_do_not_keep_stale_calculations_current(project,repo):
    source=repo/"input.csv";source.write_text("value\n10\n",encoding="utf-8")
    store=EvidenceStore(repo,project);result=store.ingest(source,units={"default":{"label":"count"}})
    graph=store.load();graph.calculate("double","x*2",{"x":result["evidence_ids"][0]},{"label":"count"});store.save(graph)
    source.write_text("value\n",encoding="utf-8");store.refresh(result["source_id"])
    assert store.load().resolve("double")["status"]=="stale"


def test_xlsx_cells_and_uncached_formulas_are_not_fabricated(project,repo):
    from openpyxl import Workbook
    source=repo/"workbook.xlsx";workbook=Workbook();sheet=workbook.active;sheet.title="Sales";sheet["A1"]=100;sheet["A2"]="=A1*2";workbook.save(source)
    store=EvidenceStore(repo,project);result=store.ingest(source,units={"default":{"label":"currency","currency":"IDR"}})
    graph=store.load();nodes=[graph.resolve(i) for i in result["evidence_ids"]]
    assert next(n for n in nodes if n["locator"]=="sheet:Sales!A1")["value"]==100
    formula=next(n for n in nodes if n["locator"]=="sheet:Sales!A2")
    assert formula["status"]=="unverified" and formula["value"] is None
    with pytest.raises(StudioError):graph.calculate("bad","x*2",{"x":formula["evidence_id"]},{"label":"currency"})


def test_native_document_and_table_extractors(repo):
    from docx import Document
    import pymupdf
    docx=repo/"memo.docx";document=Document();document.add_paragraph("Evidence text");document.add_table(rows=1,cols=2).cell(0,1).text="Table value";document.save(docx)
    assert any(r["locator"]=="paragraph:0" and r["value"]=="Evidence text" for r in extract(docx)["records"])
    assert any(r["kind"]=="cell" and r["value"]=="Table value" for r in extract(docx)["records"])
    pdf=repo/"report.pdf";document=pymupdf.open();page=document.new_page();page.insert_text((50,50),"Source evidence");document.save(pdf);document.close()
    assert "Source evidence" in extract(pdf)["records"][0]["value"]
    text=repo/"notes.md";text.write_text("Header\nEvidence paragraph\n",encoding="utf-8")
    assert extract(text)["records"][1]["locator"]=="line:2"
    structured=repo/"structured.json";structured.write_text('{"sales":{"net":42}}',encoding="utf-8")
    assert extract(structured)["records"]==[{"locator":"$/sales/net","value":42,"kind":"json_value"}]


@pytest.mark.parametrize("formula",["__import__('os').system('unsafe')","x.__class__","x[0]","2**100000000","[x for x in range(3)]"])
def test_calculation_cannot_execute_source_instructions(formula):
    with pytest.raises(StudioError):calculate(formula,{"x":2})


def test_independent_numeric_verification_and_cycle_rejection():
    assert calculate("(revenue-cost)/revenue",{"revenue":"100","cost":"60"})=="0.4"
    assert verify_number("40","40") and not verify_number("41","40")
    with pytest.raises(StudioError):calculate("x/0",{"x":10})
    graph=DependencyGraph();graph.register("claim",["calc"])
    with pytest.raises(StudioError):graph.register("calc",["claim"])
    assert graph.dependencies=={"claim":["calc"]}


def test_units_scales_and_currency_conversion_have_dimensional_provenance():
    usd={"label":"currency","currency":"USD"};idr={"label":"currency","currency":"IDR"}
    with pytest.raises(StudioError):calculate("a+b",{"a":2,"b":100},{"a":usd,"b":idr},{**idr,"transformation":"convert"})
    rate={"label":"exchange_rate","dimensions":{"currency:IDR":1,"currency:USD":-1}}
    assert calculate("amount*rate",{"amount":2,"rate":15500},{"amount":usd,"rate":rate},idr)=="31000"
    thousand={**idr,"scale":1000}
    assert calculate("revenue-cost",{"revenue":100,"cost":60},{"revenue":thousand,"cost":thousand},thousand)=="40"
    with pytest.raises(StudioError):calculate("amount/amount",{"amount":2},{"amount":usd},usd)
    from decimal import localcontext
    with localcontext() as context:
        context.prec=3
        assert calculate("x/3",{"x":1})=="0.3333333333333333333333333333"
