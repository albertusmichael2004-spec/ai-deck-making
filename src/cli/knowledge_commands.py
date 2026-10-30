

def add_parser(commands):
    parser=commands.add_parser("knowledge")
    parser.add_argument("action",choices=["ingest","retrieve","status"])
    parser.add_argument("--package",default="consulting_deck_knowledge_v1")
    parser.add_argument("--query",default="")
    parser.add_argument("--limit",type=int,default=8)
    parser.add_argument("--topic")
    parser.add_argument("--kind")


def execute(root,args):
    from knowledge.store import KnowledgeStore
    store=KnowledgeStore(root)
    if args.action=="ingest":return store.ingest(args.package)
    if args.action=="retrieve":return store.retrieve(args.query,args.limit,args.topic,args.kind)
    from state.io import read_json
    return read_json(store._package(args.package)/"ingestion_manifest.json")
