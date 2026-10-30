from collections import defaultdict
from uuid import uuid4


def reconcile(findings,sources,independent_sources=2):
    by_context=defaultdict(list)
    for finding in findings:
        context=tuple(str(finding.get(key)) for key in ["period","definition","geography","unit"])
        by_context[context].append(finding)
    conflicts=[];accepted=[]
    for context,items in by_context.items():
        values={str(item["value"]) for item in items}
        definitive=[item for item in items if sources[item["source_id"]]["quality"]["definitive_primary"]]
        if len(values)>1:
            if len({str(item["value"]) for item in definitive})==1 and definitive:
                chosen=definitive[0]
                conflicts.append({"conflict_id":"conflict_"+uuid4().hex,"status":"resolved","reason":"definitive_primary_with_matching_definition_period","sources":[item["source_id"] for item in items],"selected_source":chosen["source_id"]})
                accepted.append(chosen)
            else:conflicts.append({"conflict_id":"conflict_"+uuid4().hex,"status":"unresolved","reason":"credible_values_disagree_in_same_context","sources":[item["source_id"] for item in items],"values":list(values)})
        else:
            groups={sources[item["source_id"]]["independence_group"] for item in items}
            if definitive or len(groups)>=independent_sources:accepted.append(items[0])
    if len(by_context)>1:
        conflicts.append({"conflict_id":"conflict_"+uuid4().hex,"status":"conditional","reason":"different_period_definition_geography_or_units","contexts":[list(context) for context in by_context],"sources":[item["source_id"] for item in findings]})
    return accepted,conflicts
