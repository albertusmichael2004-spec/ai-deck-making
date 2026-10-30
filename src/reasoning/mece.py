from collections import defaultdict


def check_mece(issues,universe):
    findings=[];by_id={row["issue_id"]:row for row in issues};siblings=defaultdict(list)
    if len(by_id)!=len(issues):findings.append("duplicate_issue_identity")
    for row in issues:
        parent=row["parent_id"]
        if parent is not None and parent not in by_id:findings.append("missing_issue_parent")
        siblings[parent].append(row)
        seen={row["issue_id"]}
        while parent is not None and parent in by_id:
            if parent in seen:findings.append("issue_tree_cycle");break
            seen.add(parent);parent=by_id[parent]["parent_id"]
    for parent,children in siblings.items():
        expected=set(universe if parent is None else by_id.get(parent,{}).get("coverage_keys",[]))
        covered=set()
        for child in children:
            keys=set(child["coverage_keys"])
            if covered&keys:findings.append("overlapping_issue_coverage")
            covered|=keys
        if expected!=covered:findings.append("incomplete_issue_coverage")
    return sorted(set(findings))
