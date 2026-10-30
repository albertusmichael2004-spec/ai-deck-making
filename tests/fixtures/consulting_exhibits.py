from copy import deepcopy

from evidence.store import EvidenceStore
from evidence.context import EvidenceContext
from state.io import read_json


def prepare(repository,project,types=("bar","line","waterfall","table","matrix","roadmap","scenario","recommendation","issue_tree","timeline")):
    source=project.path/"work/metrics.csv"
    source.write_text("category,value,trend_month,trend_value\nOpening,10,January,10\nMaterials,-4,February,9\nLabor,1,March,8\nClosing,7,April,7\n",encoding="utf-8")
    store=EvidenceStore(repository,project)
    report=store.ingest(source,units={"value":{"label":"margin points"},"trend_value":{"label":"margin points"},"default":{"label":"text"}},data_period="2025")
    graph=store.load();by_locator={row["locator"]:key for key,row in graph.value["nodes"].items()}
    names=[by_locator[f"row:{i}/column:category"] for i in range(2,6)];numbers=[by_locator[f"row:{i}/column:value"] for i in range(2,6)]
    brief=read_json(__import__("pathlib").Path(__file__).with_name("basic_spec.json"))["brief"]
    brief["page_budget"]=len(types);brief["constraints"]["sources_required"]=True
    slides=[]
    for index,kind in enumerate(types):
        slide_id="exhibit_"+str(index);exhibit={"type":kind}
        if kind in {"bar","column","line","area","pie","stacked_bar","waterfall","bridge","scatter","bubble"}:
            indices=[0,3] if kind=="pie" else list(range(4))
            if kind=="bar":indices=[1,2]
            category_ids=names;value_ids=numbers
            if kind=="line":category_ids=[by_locator[f"row:{i}/column:trend_month"] for i in range(2,6)];value_ids=[by_locator[f"row:{i}/column:trend_value"] for i in range(2,6)]
            exhibit.update({"binding_id":"b_"+str(index),"category_evidence_ids":[category_ids[i] for i in indices],"series":[{"name":"Margin contribution","evidence_ids":[value_ids[i] for i in indices]}],"unit":"margin points","period":"2025"})
            used=[*[category_ids[i] for i in indices],*[value_ids[i] for i in indices]]
            graph.bind(exhibit["binding_id"],used,slide_id,"chart_"+str(index))
            if kind in {"scatter","bubble"}:
                trend=[by_locator[f"row:{i}/column:trend_value"] for i in range(2,6)]
                exhibit["series"].append({"name":"Trend observation","evidence_ids":trend,"unit":"margin points"})
                if kind=="bubble":exhibit["series"].append({"name":"Observation size","evidence_ids":trend,"unit":"margin points"})
                graph.value["bindings"][exhibit["binding_id"]]["evidence_ids"]=[*used,*trend]
                graph.dependencies.dependencies[exhibit["binding_id"]]=[*used,*trend]
        elif kind in {"table","matrix"}:
            exhibit.update({"binding_id":"b_"+str(index),"headers":["Driver","Margin points"],"rows":[[name,number] for name,number in zip(names,numbers,strict=True)]})
            graph.bind(exhibit["binding_id"],[*names,*numbers],slide_id,"table_"+str(index))
        else:exhibit["items"]=[{"title":"Diagnose material losses","body":"Validate source drivers before committing to savings."},{"title":"Test feasible actions","body":"Protect operating reliability and validate the economics."},{"title":"Review the decision","body":"Reassess performance before scaling the response."}]
        if kind=="issue_tree":exhibit["items"]=[{"id":"root","parent_id":None,"title":"Recover margin responsibly","body":"Balance economics and operating constraints."},{"id":"economics","parent_id":"root","title":"Validate cost drivers","body":"Test the material contribution."},{"id":"execution","parent_id":"root","title":"Protect reliability","body":"Validate feasible actions."}]
        if kind=="scenario":exhibit["items"]=[{"title":"Base condition","body":"Maintain reliability while diagnosing material pressure."},{"title":"Upside condition","body":"Test recovery actions if supplier alternatives validate."},{"title":"Downside condition","body":"Preserve liquidity if cost pressure persists."}]
        if kind=="recommendation":exhibit["items"]=[{"title":"Prioritize material review","body":"Validate the recorded contribution and its drivers."},{"title":"Protect reliability","body":"Test feasible actions before committing savings."},{"title":"Review before scaling","body":"Require measured economics and risk evidence."}]
        slides.append({"schema_version":"1.0","slide_id":slide_id,"purpose":"analysis","action_title":"Materials explain the largest recorded margin pressure","key_message":"The supplied contribution data identify where management should investigate first.","claim_ids":[numbers[1]],"exhibit":exhibit,"layout":{"archetype":"consulting"},"insights":[],"source_note_ids":[report["source_id"]],"brand_profile":"default_consulting"})
        if kind=="line":slides[-1]["action_title"]="Margin declines steadily across the supplied monthly observations"
        if kind=="bar":slides[-1]["annotations"]=[{"target":"exhibit","intent":"Materials contribute -4 margin points; validate root causes before action."}]
        if kind in {"roadmap","scenario","recommendation","issue_tree","timeline"}:
            titles={"roadmap":"Stage validation before committing recovery actions","scenario":"Use conditional scenarios to test the recovery decision","recommendation":"Prioritize material review while protecting operating reliability","issue_tree":"Decompose margin recovery into economics and execution","timeline":"Sequence validation before approving recovery actions"}
            slides[-1]["action_title"]=titles[kind];slides[-1]["key_message"]="The proposed structure guides validation; it does not establish feasible savings."
    store.save(graph)
    deck={"schema_version":"1.0","deck_id":"consulting-fixture","brief_id":brief["brief_id"],"core_answer":"Prioritize investigation of material costs","storyline":[row["purpose"] for row in slides],"slide_ids":[row["slide_id"] for row in slides],"canvas":{"width_in":13.333333,"height_in":7.5}}
    return brief,deck,slides,EvidenceContext(graph,project.policy),store
