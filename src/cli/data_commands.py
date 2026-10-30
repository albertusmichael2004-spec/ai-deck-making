from pathlib import Path



def add_parser(commands):
    parser=commands.add_parser("data")
    parser.add_argument("action",choices=["ingest","refresh","calculate","claim","bind","trace","verify","gaps","inventory"])
    parser.add_argument("project_id")
    parser.add_argument("--source",type=Path)
    parser.add_argument("--source-id")
    parser.add_argument("--request",type=Path)
    parser.add_argument("--evidence-id")
    parser.add_argument("--displayed")


def execute(root,args):
    from evidence.store import EvidenceStore
    from evidence.verification import EvidenceVerifier
    from ir.validation import validate
    from state.io import read_json
    from state.project import Project
    from state.errors import StudioError,ErrorCode
    project=Project.open(root,args.project_id)
    store=EvidenceStore(root,project,read_roots=[root,*([args.source.resolve()] if args.source else [])])
    if args.action=="ingest":
        if args.source is None:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Ingest requires --source")
        metadata=read_json(store.registry.policy.check(args.request)) if args.request else {"schema_version":"1.0"}
        validate(root,"source_metadata",metadata)
        return store.ingest(args.source,units=metadata.get("units"),source_date=metadata.get("source_date"),data_period=metadata.get("data_period"))
    graph=store.load()
    if args.action=="refresh":
        if args.source_id not in graph.value["sources"]:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Refresh requires a registered --source-id")
        original=Path(graph.value["sources"][args.source_id]["original_path"])
        return EvidenceStore(root,project,read_roots=[root,original]).refresh(args.source_id)
    if args.action=="inventory":
        return {"sources":graph.value["sources"],"nodes":len(graph.value["nodes"]),"unresolved":[key for key,value in graph.value["nodes"].items() if value["status"]!="current"]}
    if args.action=="trace":return graph.trace(args.evidence_id)
    if args.action=="verify":
        verifier=EvidenceVerifier(project.policy)
        value=verifier.value(graph,args.evidence_id)
        return {"evidence_id":args.evidence_id,"raw_recomputed_value":value,"passed":args.displayed is None or verifier.displayed(graph,args.evidence_id,args.displayed)}
    if args.request is None:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"This data operation requires --request")
    request=read_json(store.registry.policy.check(args.request))
    if args.action=="gaps":
        validate(root,"evidence_questions",request)
        return graph.gaps(request)
    schema={"calculate":"calculation_request","claim":"evidence_claim","bind":"data_binding"}[args.action]
    validate(root,schema,request)
    if args.action=="calculate":
        identifier=graph.calculate(request["calculation_id"],request["formula"],request["inputs"],request["unit"])
        EvidenceVerifier(project.policy).value(graph,identifier)
    elif args.action=="claim":identifier=graph.register(request)
    else:
        graph.bind(request["binding_id"],request["evidence_ids"],request["slide_id"],request["exhibit_id"])
        identifier=request["binding_id"]
    store.save(graph)
    return {"status":"registered","id":identifier}
