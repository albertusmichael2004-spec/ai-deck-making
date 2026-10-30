from state.errors import ErrorCode, StudioError


def validate_scope(patch: dict, scope: dict):
    targets = {(item["slide_id"], item["object_id"]) for item in patch["operations"]}
    allowed = {(item["slide_id"], item["object_id"]) for item in scope["objects"] if item["protection"] in {"MUST_CHANGE", "MAY_CHANGE"}}
    required = {(item["slide_id"], item["object_id"]) for item in scope["objects"] if item["protection"] == "MUST_CHANGE"}
    if not targets <= allowed or not required <= targets:
        raise StudioError(ErrorCode.SECURITY_BLOCK, "Patch violates explicit object scope")
    return required
