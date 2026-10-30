from enum import StrEnum


class Severity(StrEnum):
    BLOCKER = "BLOCKER"
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    STYLE = "STYLE"


def issue(code, severity, slide_id, object_id, message):
    return {"code": code, "severity": severity.value, "slide_id": slide_id, "object_id": object_id, "message": message}


def report(issues):
    failures = [item for item in issues if item["severity"] in {Severity.BLOCKER, Severity.MAJOR}]
    return {"passed": not failures, "errors": failures, "issues": issues}
