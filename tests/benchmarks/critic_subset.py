import importlib.util
from pathlib import Path

from preferences.store import PreferenceStore
from state.io import read_json


def cases(root):
    def isolated_native_model_review():
        result=read_json(root/"implementation/PHASE_REPORTS/phase_8_live_smoke.json");review=result["review"]
        checks={"real_native_qa":result["native_qa"],"isolated_context":result["model_context_isolated"] and review["context_isolated"],"actual_image_review":review["images_reviewed"]==3,"quality_threshold":review["score"]>=90,"complete_slide_review":len(review["slides"])==3,"no_blockers_or_major":not review["errors"],"measured_no_tool_usage":review["usage"]["tokens"]>0 and review["usage"]["queries"]==0}
        return {"passed":all(checks.values()),"score":review["score"],"threshold":90,"checks":checks}

    def factual_neutral_preference_learning():
        from uuid import uuid4
        import shutil
        repository=root/"runtime/preference_benchmark"/uuid4().hex
        if not repository.resolve().is_relative_to((root/"runtime").resolve()):raise ValueError("Benchmark output must remain in runtime")
        repository.mkdir(parents=True)
        for name in ["schemas","config"]:shutil.copytree(root/name,repository/name)
        store=PreferenceStore(repository)
        store.record("Change 20% to 25%","chart_left_insight_right",event_id="correct",declared_type="DESIGN_FEEDBACK",polarity="negative")
        neutral=store.score("chart_left_insight_right")["score"]==0
        for index in range(3):store.record("This chart layout is clear","chart_left_insight_right",event_id="approve"+str(index),polarity="positive")
        ranking=store.rerank([{"pattern":"chart_left_insight_right","score":.8},{"pattern":"generic_cards","score":.9}])
        checks={"factual_correction_neutral":neutral,"repeated_design_learning":store.score("chart_left_insight_right")["score"]>.5,"reranking":ranking[0]["pattern"]=="chart_left_insight_right"}
        return {"passed":all(checks.values()),"score":100*sum(checks.values())/len(checks),"checks":checks}
    return [isolated_native_model_review,factual_neutral_preference_learning]
