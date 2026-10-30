from copy import deepcopy
from uuid import uuid4

from state.io import read_yaml
from state.errors import StudioError,ErrorCode
from ir.validation import validate


class ResearchPlanner:
    def __init__(self,repository):self.repository=repository;self.configuration=read_yaml(repository/"config/research/modes.yaml")

    def plan(self,decision_question,gaps,mode="auto",external_allowed=True,budgets=None,hypotheses=()):
        if mode not in {*self.configuration["modes"],"auto"}:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Unknown research mode")
        material=[gap for gap in gaps if gap.get("material",True)]
        selected=("deep" if len(material)>1 or any(gap.get("uncertainty",1)>.5 for gap in material) else "standard") if mode=="auto" else mode
        if mode=="auto" and not material:selected="off"
        if not external_allowed:selected="off"
        limits=deepcopy(self.configuration["modes"][selected])
        if budgets:
            for key,value in budgets.items():
                if key not in limits or type(value) not in {int,float} or value<0:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Invalid research budget")
                limits[key]=min(limits[key],value)
        questions=[{"question_id":gap["question_id"],"question":gap["question"],"critical":gap.get("material",True),"preferred_source_types":gap.get("preferred_source_types",["official_statistics","regulator","company_filing","original_research"]),"max_age_days":gap.get("max_age_days"),"period":gap.get("period"),"geography":gap.get("geography"),"definition":gap.get("definition"),"answer_type":gap.get("answer_type","text")} for gap in gaps]
        plan={"schema_version":"1.0","research_id":"res_"+uuid4().hex,"decision_question":decision_question,"requested_mode":mode,"mode":selected,"external_allowed":external_allowed,"questions":questions,"hypotheses":list(hypotheses),"budgets":limits,"completion_policy":{"critical_questions_required":True,"unresolved_critical_conflicts_allowed":False}}
        validate(self.repository,"research_plan",plan)
        if len({row["question_id"] for row in questions})!=len(questions):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Research question identities must be unique")
        return plan

    @staticmethod
    def queries(question,hypotheses=(),iteration=0):
        core=question["question"]
        qualifiers=" ".join(str(question.get(key) or "") for key in ["geography","period","definition"]).strip()
        variants=[(core+" "+qualifiers+" official primary source data methodology").strip(),(core+" "+qualifiers+" alternative explanation limitations contradictory evidence").strip()]
        for hypothesis in hypotheses:
            variants.append(core+" evidence against "+hypothesis["text"])
        if iteration:variants.append(core+" updated original report definition clarification "+str(iteration))
        return list(dict.fromkeys(variants))
