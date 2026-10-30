def allocate(story,page_budget,appendix_budget=0):
    ordered=sorted(story["arguments"],key=lambda row:row["priority"],reverse=True)
    available=min(len(ordered),max(0,page_budget-1))
    appendix_count=min(appendix_budget,max(0,available-1))
    main_count=max(0,available-appendix_count)
    body=ordered[:main_count];appendix=ordered[main_count:main_count+appendix_count]
    # The answer page includes all core arguments; detailed overflow is explicitly omitted, never hidden.
    return {"page_budget":page_budget,"main":[{"role":"executive_summary","title":story["core_answer"]["text"],"argument_ids":story["core_answer"]["argument_ids"]},*[{"role":"argument","title":row["action_title"],"argument_ids":[row["argument_id"]]} for row in body]],"appendix":[{"role":"appendix","title":row["action_title"],"argument_ids":[row["argument_id"]]} for row in appendix],"omitted_argument_ids":[row["argument_id"] for row in ordered[main_count+appendix_count:]],"executive_summary":[{"argument_id":key,"text":next(row["claim"] for row in story["arguments"] if row["argument_id"]==key)} for key in story["core_answer"]["argument_ids"]]}
