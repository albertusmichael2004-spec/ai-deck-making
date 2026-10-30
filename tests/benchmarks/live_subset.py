from state.io import read_json


def cases(root):
    def native_live_model_revision():
        result=read_json(root/"implementation/PHASE_REPORTS/phase_10_model_native.json")
        checks={"native_qa":all(row["passed"] for row in result["native_reviews"]),"isolated_critic":all(row["passed"] and row["score"]>=90 and row["context_isolated"] for row in result["model_reviews"]),"measured_tokens":result["tokens"]>0,"unsaved_preserved":result["unsaved_preserved"]}
        return {"passed":result["passed"] and all(checks.values()),"score":min(row["score"] for row in result["model_reviews"]),"checks":checks}
    def native_selection_comment_recovery():
        reports={key:read_json(root/("implementation/PHASE_REPORTS/phase_10_"+key+".json")) for key in ["native_case","comments_native","table_native","recovery_native"]}
        return {"passed":all(row["passed"] for row in reports.values()),"score":100 if all(row["passed"] for row in reports.values()) else 0,"reports":reports}
    return [native_live_model_revision,native_selection_comment_recovery]
