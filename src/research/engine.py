import base64
from collections import deque
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit

from evidence.store import EvidenceStore,identity
from research.budget import ResearchBudget
from research.cache import ResearchCache
from research.conflicts import reconcile
from research.plan import ResearchPlanner
from research.quality import canonical_url,source_quality,content_fingerprint,validate_finding
from research.snapshot import extract_snapshot
from research.state import ResearchState
from state.errors import StudioError,ErrorCode
from state.io import read_yaml,read_json,write_json,sha256,atomic_bytes
from state.locking import FileLock


def shingles(text):
    words=text.lower().split()
    return {tuple(words[i:i+5]) for i in range(max(0,len(words)-4))}


class ResearchEngine:
    """Provider-independent evidence acquisition. No presentation mutations."""
    def __init__(self,repository,project,search,fetcher,extractor):
        self.repository,self.project=repository,project
        self.search,self.fetcher,self.extractor=search,fetcher,extractor
        self.state=ResearchState(project)
        self.cache=ResearchCache(project.path/"work/research_cache")
        self.publishers=read_yaml(repository/"config/research/publishers.yaml")["publishers"]
        self.settings=read_yaml(repository/"config/research/modes.yaml")

    def run(self,plan,refresh=False):
        with FileLock(self.project.policy.check(self.project.path/"work/research.lock",write=True)):
            return self._run(plan,refresh)

    def _meter(self,provider,budget):
        usage=getattr(provider,"last_usage",{"tokens":0,"queries":0})
        self.state.event("provider_usage",**usage)
        # Logical discovery calls were reserved before invocation. Additional native searches are measured.
        extra={}
        if usage.get("queries",0)>1:extra["queries"]=usage["queries"]-1
        if usage.get("tokens",0):extra["tokens"]=usage["tokens"]
        budget.account_usage(extra)

    def _discover(self,query,budget,refresh):
        cached=None if refresh else self.cache.get("search:"+query,3600)
        if cached is not None:
            self.executed_queries.append(query);self.state.event("query_cached",query=query);return cached
        budget.consume("queries")
        budget.check_model()
        results=self.search.search(query,limit=8)
        self.executed_queries.append(query)
        self.state.event("query_executed",query=query,result_count=len(results))
        self._meter(self.search,budget)
        self.cache.put("search:"+query,results)
        return results

    def _document(self,url,budget,refresh):
        cached=None if refresh else self.cache.get("document:"+url,86400)
        if cached is not None:
            self.state.event("source_cached",url=url);return cached
        budget.consume("fetches")
        document=self.fetcher.fetch(url)
        # Round-trip decoding detects altered bytes/text from every adapter, including caches.
        extract_snapshot({"document":document,"findings":[]})
        self.state.event("source_fetched",url=document["url"],sha256=document["sha256"],http_requests=document.get("http_requests",1))
        self.cache.put("document:"+url,document)
        return document

    def _source(self,document,question,finding):
        url=canonical_url(document["url"]);host=urlsplit(url).hostname
        configured=self.publishers.get(host)
        source={"source_id":identity("web",url),"url":url,"title":document["title"],"publisher":(configured or {}).get("publisher",host),"source_type":(configured or {}).get("source_type","general_web"),"independence_group":(configured or {}).get("independence_group",host),"published_at":finding.get("published_at"),"retrieved_at":document["retrieved_at"],"period":finding.get("period"),"geography":finding.get("geography"),"definition":finding.get("definition"),"question_fit":finding.get("question_fit",0),"definitive":finding.get("definitive",False),"language":"unknown","sha256":document["sha256"]}
        fingerprint=content_fingerprint(document["text"]);tokens=shingles(document["text"])
        for prior in self.state.sources.values():
            prior_tokens={tuple(item) for item in prior.get("shingles",[])}
            union=tokens|prior_tokens
            if prior.get("content_fingerprint")==fingerprint or union and len(tokens&prior_tokens)/len(union)>=.8:
                source["independence_group"]=prior["independence_group"]
                source["syndicated_from"]=prior["source_id"];break
        source["content_fingerprint"]=fingerprint;source["shingles"]=[list(item) for item in sorted(tokens)]
        source["quality"]=source_quality(source,question)
        source["quality"]["eligible"] &= source["quality"]["authority"]>=self.settings["minimum_quality"] and source["quality"]["question_fit"]>=self.settings["minimum_fit"]
        folder=self.state.path/"documents"/source["source_id"]/document["sha256"]
        folder.mkdir(parents=True,exist_ok=True)
        raw=folder/"original.bin";decoded=folder/"document.json"
        if raw.exists() and sha256(raw)!=document["sha256"]:raise StudioError(ErrorCode.SOURCE_CONFLICT,"Saved original research bytes changed")
        if not raw.exists():
            with raw.open("xb") as stream:stream.write(base64.b64decode(document["raw_base64"],validate=True))
        if not decoded.exists():write_json(decoded,document)
        elif any(read_json(decoded)[key]!=document[key] for key in ["sha256","text_sha256","text","regions","raw_base64"]):raise StudioError(ErrorCode.SOURCE_CONFLICT,"Saved immutable research document changed")
        source["document_path"]=str(decoded);source["original_bytes_path"]=str(raw)
        prior=self.state.sources.get(source["source_id"],{})
        source["quality_by_question"]={**prior.get("quality_by_question",{}),question["question_id"]:source["quality"]}
        source["previous_versions"]=[*prior.get("previous_versions",[]),*([{key:prior[key] for key in ["sha256","document_path","original_bytes_path"]}] if prior and prior["sha256"]!=source["sha256"] else [])]
        self.state.sources[source["source_id"]]=source
        return source

    def _branch(self,question,queries,plan,budget,refresh,findings):
        discovered=[]
        count=max(1,min(len(plan["questions"]),plan["budgets"]["breadth"]))
        query_cap=max(1,plan["budgets"]["max_queries"]//count)
        source_cap=max(1,plan["budgets"]["max_fetches"]//count)
        effort=self.effort.setdefault(question["question_id"],{"queries":0,"sources":0})
        for query in queries:
            if effort["queries"]>=query_cap:break
            effort["queries"]+=1
            for result in self._discover(query,budget,refresh):
                url=canonical_url(result["url"])
                self.state.event("source_discovered",url=url,question_id=question["question_id"])
                discovered.append(url)
        # Primary domains first, while keeping all discovered leads for chained origin chasing.
        discovered=sorted(set(discovered),key=lambda url:urlsplit(url).hostname not in self.publishers)
        queue=deque((url,0) for url in discovered);seen=set()
        while queue:
            if effort["sources"]>=source_cap:break
            url,depth=queue.popleft()
            if url in seen or depth>=plan["budgets"]["depth"]:continue
            seen.add(url)
            effort["sources"]+=1
            try:
                document=self._document(url,budget,refresh)
                cache_key="extract:"+document["sha256"]+":"+question["question_id"]+":"+content_fingerprint(str(question))
                extracted=None if refresh else self.cache.get(cache_key,86400)
                if extracted is None:
                    budget.check_model()
                    extracted=self.extractor.extract(document,question)
                    self._meter(self.extractor,budget)
                    self.cache.put(cache_key,extracted)
                # Total quoted content per source remains within 25 words, not 25 per finding.
                if sum(len(row["quote"].split()) for row in extracted)>25:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Source excerpt budget exceeded")
                for finding in extracted:
                    validate_finding(finding,document)
                    source=self._source(document,question,finding)
                    if not source["quality"]["eligible"]:
                        self.state.event("source_rejected",source_id=source["source_id"],reason="quality_fit_freshness",quality=source["quality"]);continue
                    item={**finding,"source_id":source["source_id"],"question_id":question["question_id"]}
                    if item not in findings:findings.append(item)
                    self.state.event("source_accepted",source_id=source["source_id"],question_id=question["question_id"])
                    self.state.event("finding_extracted",finding=item)
                # Source chaining remains bounded separately from breadth; chase verified originals first.
                links=sorted(document["links"],key=lambda link:urlsplit(link).hostname not in self.publishers)
                queue.extend((link,depth+1) for link in links)
            except StudioError as exc:
                if exc.code in {ErrorCode.RESEARCH_BUDGET_EXHAUSTED,ErrorCode.SECURITY_BLOCK}:raise
                self.state.event("source_rejected",url=url,reason=exc.as_dict())

    def _assess(self,questions,findings):
        accepted=[];conflicts=[];scores={}
        for question in questions:
            subset=[row for row in findings if row["question_id"]==question["question_id"]]
            sources=deepcopy(self.state.sources)
            for source in sources.values():source["quality"]=source.get("quality_by_question",{}).get(question["question_id"],source["quality"])
            current=[row for row in subset if sources[row["source_id"]]["quality"]["eligible"]]
            chosen,issues=reconcile(current,sources,self.settings["independent_sources"])
            issues=[{**issue,"question_id":question["question_id"]} for issue in issues]
            accepted.extend(chosen);conflicts.extend(issues)
            scores[question["question_id"]]=1 if chosen and not any(issue["status"]=="unresolved" for issue in issues) else 0
        return accepted,conflicts,scores

    def _handoff(self,accepted):
        store=EvidenceStore(self.repository,self.project)
        results=[]
        for finding in accepted:
            source=self.state.sources[finding["source_id"]]
            document=read_json(Path(source["document_path"]))
            snapshot={"format":"studio_research_snapshot_v1","document":document,"findings":[finding],"publisher":source["publisher"]}
            extract_snapshot(snapshot)
            key=content_fingerprint(str(finding))
            path=self.state.path/"handoff"/(source["source_id"]+"_"+key+".json")
            if not path.exists():write_json(path,snapshot)
            result=store.ingest(path,units={"default":{"label":finding.get("unit") or "unspecified"}},source_date=source.get("published_at"),data_period=finding.get("period"))
            results.append({**result,"question_id":finding["question_id"],"url":source["url"],"original_sha256":source["sha256"]})
        return results

    def _run(self,plan,refresh):
        self.state.start(plan)
        self.effort={}
        self.executed_queries=[]
        budget=ResearchBudget(plan["budgets"]);findings=[];accepted=[];conflicts=[];scores={}
        questions=sorted(plan["questions"],key=lambda row:not row["critical"])
        active=questions[:plan["budgets"]["breadth"]]
        stop="external_research_off" if plan["mode"]=="off" else "iteration_budget"
        low_gain=0;previous=0;iterations=0;failure=None
        try:
            for iteration in range(plan["budgets"]["max_iterations"]):
                iterations=iteration+1;self.state.event("iteration",iteration=iteration)
                for question in active:
                    if scores.get(question["question_id"])==1:continue
                    queries=ResearchPlanner.queries(question,plan["hypotheses"],iteration)
                    if iteration:self.state.event("follow_up",question_id=question["question_id"],queries=queries)
                    self._branch(question,queries,plan,budget,refresh,findings)
                accepted,conflicts,scores=self._assess(questions,findings)
                if all(scores.get(row["question_id"],0)==1 for row in questions if row["critical"]):stop="evidence_sufficient";break
                low_gain=low_gain+1 if len(findings)==previous else 0;previous=len(findings)
                if low_gain>=self.settings["max_low_gain_iterations"]:stop="low_marginal_information_gain";break
        except StudioError as exc:
            failure=exc.as_dict();stop="budget_reached" if exc.code==ErrorCode.RESEARCH_BUDGET_EXHAUSTED else "capability_or_security_block"
            accepted,conflicts,scores=self._assess(questions,findings)
        for issue in conflicts:
            self.state.conflicts[issue["conflict_id"]]=issue;self.state.event("conflict_found",conflict=issue)
        unresolved=[row for row in questions if row["critical"] and not scores.get(row["question_id"])]
        complete=not unresolved and stop=="evidence_sufficient"
        # A security failure prevents handoff even of earlier accepted findings.
        handoff=[] if failure and failure["code"]==ErrorCode.SECURITY_BLOCK.value else self._handoff(accepted)
        result={"schema_version":"1.0","research_id":plan["research_id"],"complete":complete,"stop_reason":stop,"iterations":iterations,"usage":budget.used,"sufficiency":scores,"findings":findings,"accepted":accepted,"conflicts":conflicts,"evidence_handoff":handoff,"unknowns":[{"question_id":row["question_id"],"question":row["question"],"reason":stop,"confidence_impact":"insufficient_for_material_claim","next_action":"Retrieve primary evidence or clarify period/definition"} for row in unresolved],"failure":failure}
        result["hypotheses"]=[{"text":hypothesis["text"],"status":"requires_explicit_interpretation","counter_search_performed":any("evidence against "+hypothesis["text"] in query for query in self.executed_queries),"evidence_ids":[identifier for handover in handoff for identifier in handover["evidence_ids"]]} for hypothesis in plan["hypotheses"]]
        for hypothesis in result["hypotheses"]:self.state.event("hypothesis_update",hypothesis=hypothesis)
        self.state.event("research_stopped",stop_reason=stop,complete=complete,usage=budget.used)
        self.state.persist();write_json(self.state.path/"research_result.json",result)
        summary="Research "+plan["research_id"]+"\n\nStatus: "+("complete" if complete else "incomplete")+"\nStop: "+stop+"\n\n"
        summary+="\n".join("- Unknown: "+row["question"]+"; next: "+row["next_action"] for row in result["unknowns"])
        atomic_bytes(self.state.path/"research_summary.md",summary.encode())
        return result
