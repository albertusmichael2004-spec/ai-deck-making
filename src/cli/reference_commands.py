from pathlib import Path


def add_parser(commands):
    parser=commands.add_parser("references",aliases=["database"]);actions=parser.add_subparsers(dest="reference_action",required=True)
    ingest=actions.add_parser("ingest");ingest.add_argument("--dry-run",action="store_true");ingest.add_argument("--force",action="store_true")
    query=actions.add_parser("query");query.add_argument("text");query.add_argument("--content-shape");query.add_argument("--brand");query.add_argument("--limit",type=int,default=8)
    load=actions.add_parser("load");load.add_argument("reference_id");load.add_argument("slide_id");load.add_argument("--stage",choices=["metadata","preview","structure","original"],default="metadata")
    promote=actions.add_parser("promote");promote.add_argument("reference_id");promote.add_argument("slide_id");promote.add_argument("--reason",required=True)
    actions.add_parser("status")
    actions.add_parser("files")
    actions.add_parser("migrate")
    relocate=actions.add_parser("relocate");relocate.add_argument("--from-root",type=Path,required=True)
    upload=actions.add_parser("import");upload.add_argument("--source",type=Path,action="append")
    for action in actions.choices.values():
        action.add_argument("--project",dest="reference_project",help="Explicit project selected/named at the start of this task; never inferred from last selection")
        action.add_argument("--scope",choices=["database","project"],help="Storage scope for imports/ingestion/load/approval; query defaults to allowed combined scopes")


def execute(root,args):
    from presentation.rendering.native import NativeRenderer
    from references.catalog import ReferenceCatalog
    from preferences.store import PreferenceStore
    catalog=ReferenceCatalog(root,project_id=args.reference_project,renderer=NativeRenderer(root),preferences=PreferenceStore(root))
    if args.scope:catalog.store(args.scope)
    if args.reference_action=="relocate":
        from references.migration import relocate_database
        from state.errors import StudioError, ErrorCode
        if args.reference_project or args.scope=="project":raise StudioError(ErrorCode.SECURITY_BLOCK,"Relocation applies only to general Database")
        return relocate_database(root,args.from_root)
    if args.reference_action=="migrate":
        from references.migration import consolidate_unindexed
        from state.errors import StudioError, ErrorCode
        if args.reference_project or args.scope=="project":raise StudioError(ErrorCode.SECURITY_BLOCK,"Migration applies only to general Database")
        return consolidate_unindexed(root)
    if args.reference_action=="query":
        query={"text":args.text,"content_shape":args.content_shape,"brand":args.brand}
        if args.scope:return [{**row,"scope":args.scope,"project_id":args.reference_project if args.scope=="project" else None} for row in catalog.store(args.scope).query(query,args.limit)]
        return catalog.query(query,args.limit)
    if args.reference_action=="files":return catalog.files() if not args.scope else [row for row in catalog.files() if row["scope"]==args.scope]
    scope=args.scope or ("project" if args.reference_project else "database")
    store=catalog.store(scope)
    if args.reference_action=="import":
        from cli.workspace_menu import pick_files
        return {"scope":scope,"files":catalog.import_paths(args.source or pick_files(),scope=scope),"indexed":False,"next_step":"references ingest (same scope) for native PPT previews; documents stay registered references"}
    if args.reference_action=="ingest":return store.ingest(dry_run=args.dry_run,force=args.force)
    if args.reference_action=="load":return catalog.load(args.reference_id,args.slide_id,args.stage,scope=scope)
    if args.reference_action=="promote":return store.promote(args.reference_id,args.slide_id,reason=args.reason)
    return store.state()
