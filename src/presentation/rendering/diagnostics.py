"""Actionable Office failures, distinct from Codex approval prompts."""


def office_failure(exc):
    codes = []
    def visit(value):
        if type(value) is int:
            codes.append(value)
        elif isinstance(value, (tuple, list)):
            for item in value:
                visit(item)
    visit(getattr(exc, "args", ()))
    visit(getattr(exc, "hresult", None))
    message = str(exc)
    reason = "native_render_failed"
    action = "Save your work, dismiss any PowerPoint modal dialog, and retry the Studio native preflight."
    if -2147188160 in codes or "automation rights" in message.lower():
        reason = "office_automation_denied"
        action = "PowerPoint denied automation. Open the trusted local working copy, resolve any Office sign-in, permission or Protected View prompt, then retry. A Codex permission exception cannot grant Office automation rights."
    elif -2147024891 in codes:
        reason = "automation_access_denied"
        action = "Automation access was denied. Run the native preflight through the normal Codex approval flow if sandbox access is blocked; check that Office and the terminal use the same Windows user and elevation."
    elif any(code in codes for code in [-2147418111, -2147417846]):
        reason = "office_busy"
        action = "PowerPoint is busy. Finish editing or dismiss its modal dialog, then retry."
    return {"code":"CAPABILITY_UNAVAILABLE", "reason":reason, "error_type":type(exc).__name__, "hresult":getattr(exc,"hresult",None), "message":message, "recovery_action":action}


def occupied_instance(count):
    return {"code":"CAPABILITY_UNAVAILABLE", "reason":"isolated_instance_not_available", "open_presentations":count,
            "message":f"Native QA needs an isolated PowerPoint session; this instance contains {count} open presentation(s).",
            "recovery_action":"Save and close the open PowerPoint presentations yourself, then retry native QA. Studio will not close user documents or skip validation."}
