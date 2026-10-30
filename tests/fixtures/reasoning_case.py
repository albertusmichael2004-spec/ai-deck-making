from copy import deepcopy

from evidence.store import EvidenceStore
from state.io import read_json


def prepare(repository,project):
    source=project.path/"work/costs.csv"
    source.write_text("driver,margin_loss_pp\nMaterials,4\nLabor,1\n",encoding="utf-8")
    store=EvidenceStore(repository,project)
    report=store.ingest(source,units={"margin_loss_pp":{"label":"percentage points"},"default":{"label":"text"}},data_period="2025")
    graph=store.load()
    values={row["locator"]:row["evidence_id"] for row in graph.value["nodes"].values()}
    materials=values["row:2/column:margin_loss_pp"];labor=values["row:3/column:margin_loss_pp"]
    graph.calculate("ev_total","materials+labor",{"materials":materials,"labor":labor},{"label":"percentage points"})
    store.save(graph)
    brief=read_json(repository/"tests/fixtures/basic_spec.json")["brief"] if (repository/"tests/fixtures/basic_spec.json").exists() else read_json(__import__("pathlib").Path(__file__).with_name("basic_spec.json"))["brief"]
    brief["decision_required"]="Which margin recovery action should management prioritize?";brief["page_budget"]=4
    answer="Prioritize a procurement review before cost reductions elsewhere."
    story={"schema_version":"1.0","storyline_id":"candidate","decision_question":brief["decision_required"],"core_answer":{"text":answer,"recommendation_id":"r1","argument_ids":["a1","a2"]},"scqa":{"situation":"Margin declined across cost drivers.","complication":"The loss is concentrated in materials.","question":brief["decision_required"],"answer":answer},"issues":[{"issue_id":"i1","parent_id":None,"question":"Which costs explain the loss?","coverage_keys":["diagnosis"],"critical":True},{"issue_id":"i2","parent_id":None,"question":"Which action has the most leverage?","coverage_keys":["response"],"critical":True}],"hypotheses":[{"hypothesis_id":"h1","text":"Materials explain most of the margin decline","issue_ids":["i1"],"status":"supported","evidence_ids":[materials,labor],"counter_evidence_ids":[]}],"arguments":[{"argument_id":"a1","issue_id":"i1","claim":"Materials account for 4 percentage points of margin decline.","evidence_ids":[materials,labor],"numeric_assertions":[{"evidence_id":materials,"displayed":"4","unit":"percentage points"}],"implication":"Concentrate diagnosis on materials.","action_title":"Materials drive most of the margin decline","transition":"This identifies the dominant driver.","priority":.9},{"argument_id":"a2","issue_id":"i2","claim":"Materials offer the largest procurement review opportunity.","evidence_ids":[materials,labor],"numeric_assertions":[],"implication":"Test procurement actions before broader cuts.","action_title":"Focus procurement review on the dominant cost driver","transition":"The dominant driver determines the next action.","priority":.8}],"recommendations":[{"recommendation_id":"r1","text":answer,"argument_ids":["a1","a2"],"criteria":[{"criterion":"impact","assessment":"favorable","rationale":"Materials explain the largest recorded loss.","argument_ids":["a1"]}],"assumptions":["Procurement savings require validation before implementation."],"tradeoffs":["Protect supplier reliability while reviewing cost."],"next_steps":[{"action":"Validate material drivers and supplier options","owner":"Procurement lead","timing":"Before approving the recovery plan"}]}]}
    return {"brief":brief,"coverage_keys":["diagnosis","response"],"evidence_ids":[*report["evidence_ids"],"ev_total"],"appendix_budget":1},story,store


class Provider:
    last_usage={"tokens":100}
    def __init__(self,story):self.story=story;self.prompts=[]
    def complete(self,prompt,schema):self.prompts.append(prompt);return deepcopy(self.story)


class Knowledge:
    def retrieve(self,*args,**kwargs):return []
