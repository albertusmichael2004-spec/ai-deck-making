from copy import deepcopy

from layout.baseline import BaselineLayout
from layout.consulting import ConsultingLayout


class AdaptiveLayoutCompiler:
    def __init__(self,repository,preferences=None,context=None):
        self.baseline,self.consulting=BaselineLayout(repository),ConsultingLayout(repository)
        self.preferences,self.context=preferences,context or {}
    def compile(self,deck,slide,source_notes=()):
        if slide["layout"]["archetype"]=="baseline" and slide["brand_profile"]=="default_consulting" and slide["exhibit"]["type"] in {"text","shapes"}:return self.baseline.compile(deck,slide,source_notes)
        prepared=deepcopy(slide)
        if prepared["layout"]["archetype"]=="auto":
            prepared["layout"]["archetype"]="two_column" if prepared.get("insights") and "resolved_series" in prepared["exhibit"] and len(prepared["exhibit"]["resolved_categories"])<=8 else "single_exhibit"
            if self.preferences and prepared["layout"]["archetype"]=="two_column":
                candidates=[{"pattern":"two_column","score":1.0},{"pattern":"single_exhibit","score":.8}]
                ranked=self.preferences.rerank(candidates,{**self.context,"brand":slide["brand_profile"]})
                prepared["layout"]["archetype"]=ranked[0]["pattern"]
        result=self.consulting.compile(deck,prepared,source_notes)
        result["resolved_archetype"]=prepared["layout"]["archetype"]
        return result
