from state.io import read_json,sha256
from state.project import Project


def cases(root):
    def native_autonomous_repair():
        result=read_json(root/"implementation/PHASE_REPORTS/phase_9_live_smoke.json");state=result["state"]
        project=Project.open(root,result["project_id"]);history=state["history"]
        checks={"real_measured_fixture":result["fixture"] and state["tokens"]>0,"bad_copy_rejected":history[0]["critic_passed"] is False,"repair_occurred":state["iteration"]>0,"post_repair_native_qa":history[-1]["qa_passed"],"post_repair_critic":history[-1]["critic_passed"] and history[-1]["score"]>=90,"safe_commit":state["status"]=="committed" and sha256(project.canonical)==state["candidate_sha256"],"bounded":state["iteration"]<=3 and state["tokens"]<=192000}
        return {"passed":all(checks.values()),"score":history[-1]["score"],"threshold":90,"checks":checks}
    def incremental_native_regression():
        result=read_json(root/"implementation/PHASE_REPORTS/phase_9_incremental_native.json")
        checks={"one_slide_recompiled":len(result["recompiled_slides"])==1,"native_reopen_qa":result["native_qa"]["passed"],"protected_pixels":all(row["passed"] and row["changed_fraction"]==0 for row in result["protected_pixel_comparisons"]),"source_values_preserved":result["chart_values"]==[4,1]}
        return {"passed":all(checks.values()),"score":100*sum(checks.values())/len(checks),"checks":checks}
    return [native_autonomous_repair,incremental_native_regression]
