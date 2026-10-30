import base64
import json
from copy import deepcopy

import pytest

from evidence.store import EvidenceStore
from evidence.verification import EvidenceVerifier
from research.documents import decode_document
from research.engine import ResearchEngine
from research.plan import ResearchPlanner
from research.quality import canonical_url,source_quality
from research.snapshot import extract_snapshot
from state.errors import StudioError,ErrorCode
from state.io import write_yaml


class Search:
    last_usage={"tokens":0,"queries":0}
    def __init__(self,urls):self.urls=urls;self.queries=[]
    def search(self,query,limit):self.queries.append(query);return [{"url":url,"title":"fixture"} for url in self.urls][:limit]


class Fetch:
    def __init__(self,documents):self.documents=documents;self.calls=[]
    def fetch(self,url):self.calls.append(url);return deepcopy(self.documents[url])


class Extract:
    last_usage={"tokens":0,"queries":0}
    def __init__(self,findings):self.findings=findings;self.calls=[]
    def extract(self,document,question):self.calls.append(document["url"]);return deepcopy(self.findings[document["url"]])


def doc(url,value="10",extra="",links=()):
    raw=(f"Measurement is {value} units for 2025. "+extra).encode()
    return {**decode_document(raw,"text/plain",url),"url":url,"requested_url":url,"raw_base64":base64.b64encode(raw).decode(),"retrieved_at":"2026-10-11T00:00:00+00:00","http_requests":1,"mime":"text/plain","trust":"untrusted_data","links":list(links)}


def finding(value="10",definitive=False):
    return {"value":value,"unit":"units","period":"2025","geography":"global","definition":"measurement","published_at":"2026-01-01","quote":f"Measurement is {value} units for 2025.","locator":"document:text","question_fit":1,"definitive":definitive,"answer_type":"numeric"}


def plan(repo,mode="standard",**kwargs):
    return ResearchPlanner(repo).plan("What decision is supported?",[{"question_id":"q1","question":"What is the measurement?","period":"2025","geography":"global","definition":"measurement","answer_type":"numeric"}],mode=mode,**kwargs)


def engine(repo,project,documents,findings,primary=False):
    write_yaml(repo/"config/research/publishers.yaml",{"schema_version":"1.0","publishers":{url.split('/')[2]:{"publisher":url.split('/')[2],"source_type":"official_statistics" if primary else "independent_news","independence_group":url.split('/')[2]} for url in documents}})
    return ResearchEngine(repo,project,Search(list(documents)[:1] if any(row["links"] for row in documents.values()) else list(documents)),Fetch(documents),Extract(findings))


def test_triangulation_handoff_independent_reverification_cache(repo,project):
    documents={"https://a.test/report":doc("https://a.test/report",extra="Author alpha measured population directly."),"https://b.test/report":doc("https://b.test/report",extra="Independent beta survey provides a separate study.")}
    findings={url:[finding()] for url in documents}
    service=engine(repo,project,documents,findings)
    result=service.run(plan(repo))
    assert result["complete"] and result["stop_reason"]=="evidence_sufficient"
    assert len(result["evidence_handoff"])==1
    graph=EvidenceStore(repo,project).load()
    identifier=result["evidence_handoff"][0]["evidence_ids"][0]
    assert EvidenceVerifier(project.policy).value(graph,identifier)=="10"
    assert any("contradictory" in query for query in service.search.queries)
    calls=len(service.fetcher.calls)
    assert service.run(plan(repo))["complete"]
    assert len(service.fetcher.calls)==calls
    assert service.run(plan(repo),refresh=True)["complete"]
    assert len(service.fetcher.calls)>calls
    records=[json.loads(row) for row in (service.state.path/"research_ledger.jsonl").read_text().splitlines()]
    assert any(row["event"]=="query_cached" for row in records)


def test_syndicated_sources_do_not_triangulate(repo,project):
    documents={url:doc(url) for url in ["https://a.test/report","https://b.test/report"]}
    result=engine(repo,project,documents,{url:[finding()] for url in documents}).run(plan(repo))
    assert not result["complete"] and not result["accepted"]
    assert result["unknowns"][0]["confidence_impact"]=="insufficient_for_material_claim"


def test_conflict_not_averaged_and_primary_resolution(repo,project):
    documents={"https://a.test/report":doc("https://a.test/report","10"),"https://b.test/report":doc("https://b.test/report","12",extra="Different survey source.")}
    service=engine(repo,project,documents,{"https://a.test/report":[finding()],"https://b.test/report":[finding("12")]})
    result=service.run(plan(repo))
    assert not result["complete"] and result["conflicts"][0]["status"]=="unresolved"
    assert result["evidence_handoff"]==[]
    service=engine(repo,project,documents,{"https://a.test/report":[finding(definitive=True)],"https://b.test/report":[finding("12")]},primary=True)
    result=service.run(plan(repo),refresh=True)
    assert result["complete"] and result["accepted"][0]["value"]=="10"
    assert result["conflicts"][0]["status"]=="resolved"


def test_depth_chases_original_breadth_and_off_independent(repo,project):
    a,b="https://a.test/report","https://b.test/original"
    documents={a:doc(a,links=[b]),b:doc(b,extra="This is the original study.")}
    service=engine(repo,project,documents,{a:[],b:[finding(definitive=True)]},primary=True)
    assert service.run(plan(repo,budgets={"depth":2}))["complete"]
    service=engine(repo,project,documents,{a:[],b:[finding(definitive=True)]},primary=True)
    assert not service.run(plan(repo,budgets={"depth":1}),refresh=True)["complete"]
    before=len(service.fetcher.calls)
    result=service.run(plan(repo,external_allowed=False))
    assert result["stop_reason"]=="external_research_off" and len(service.fetcher.calls)==before


def test_budget_never_becomes_sufficiency(repo,project):
    url="https://a.test/report";service=engine(repo,project,{url:doc(url)},{url:[finding(definitive=True)]},primary=True)
    result=service.run(plan(repo,budgets={"max_queries":0}))
    assert not result["complete"] and result["stop_reason"]=="budget_reached"
    assert result["usage"]["queries"]==0 and result["unknowns"]


def test_zero_tokens_prevents_calls_and_substring_unit_forgery(repo,project):
    url="https://a.test/report";service=engine(repo,project,{url:doc(url)},{url:[finding(definitive=True)]},primary=True)
    result=service.run(plan(repo,budgets={"max_tokens":0}))
    assert not result["complete"] and service.search.queries==[]
    wrong=finding();wrong["quote"]="Measurement is 110 units for 2025."
    with pytest.raises(StudioError):extract_snapshot({"document":doc(url,"110"),"findings":[wrong]})
    wrong=finding();wrong["unit"]="billions"
    with pytest.raises(StudioError):extract_snapshot({"document":doc(url),"findings":[wrong]})


def test_untrusted_publisher_claim_and_wrong_quote_rejected(repo,project):
    url="https://unknown.test/report";service=ResearchEngine(repo,project,Search([url]),Fetch({url:doc(url)}),Extract({url:[finding(definitive=True)]}))
    result=service.run(plan(repo))
    assert not result["complete"] and not result["accepted"]
    wrong=finding();wrong["quote"]="Measurement is 99 units for 2025."
    with pytest.raises(StudioError):extract_snapshot({"document":doc(url),"findings":[wrong]})
    wrong=finding();wrong["locator"]="page:999"
    with pytest.raises(StudioError):extract_snapshot({"document":doc(url),"findings":[wrong]})


def test_raw_snapshot_tampering_rejected():
    document=doc("https://a.test/report");document["text"]="Invented fact 999"
    with pytest.raises(StudioError) as error:extract_snapshot({"document":document,"findings":[]})
    assert error.value.code==ErrorCode.SOURCE_CONFLICT


def test_counter_hypothesis_and_measured_overrun_stop(repo,project):
    url="https://a.test/report";service=engine(repo,project,{url:doc(url)},{url:[finding(definitive=True)]},primary=True)
    result=service.run(plan(repo,hypotheses=[{"text":"Measurement increased"}]))
    assert result["hypotheses"][0]["counter_search_performed"]
    assert any("evidence against Measurement increased" in query for query in service.search.queries)
    service=engine(repo,project,{url:doc(url)},{url:[finding(definitive=True)]},primary=True)
    service.search.last_usage={"queries":2,"tokens":90000}
    result=service.run(plan(repo),refresh=True)
    assert not result["complete"] and result["usage"]["tokens"]==90000 and result["usage"]["queries"]==2
    assert len(service.search.queries)==1
    assert not service.fetcher.calls
    records=[json.loads(row) for row in (service.state.path/"research_ledger.jsonl").read_text().splitlines()]
    assert any(row["event"]=="provider_usage" and row.get("tokens")==90000 for row in records)


def test_url_security_freshness_and_auto(repo):
    for url in ["file:///C:/secret","https://user:pass@example.org/"]:
        with pytest.raises(StudioError):canonical_url(url)
    assert canonical_url("https://example.org/?utm_source=x&a=2#secret")=="https://example.org/?a=2"
    assert not source_quality({"source_type":"official_statistics","question_fit":1,"period":"2024"},{"period":"2025"})["eligible"]
    assert plan(repo,mode="auto")["mode"]=="deep"
    assert plan(repo,mode="quick")["budgets"]["breadth"]!=plan(repo,mode="quick")["budgets"]["depth"] or plan(repo,budgets={"breadth":1,"depth":2})["budgets"]["depth"]==2
