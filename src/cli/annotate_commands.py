"""Deck preview and click-annotation commands used by the VS Code Deck Preview and agents."""

from state.errors import StudioError, ErrorCode


def add_parser(commands):
    parser = commands.add_parser("annotate")
    parser.add_argument("action", choices=["preview", "add", "list", "request", "done", "dismiss"])
    parser.add_argument("project_id", nargs="?")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--slide")
    parser.add_argument("--object", action="append", default=[])
    parser.add_argument("--region", help="x,y,width,height as fractions of the slide")
    parser.add_argument("--text")
    parser.add_argument("--id", action="append", default=[])
    parser.add_argument("--all", action="store_true")


def _region(value):
    if value is None:
        return None
    try:
        region = [float(part) for part in value.split(",")]
    except ValueError as exc:
        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Region must be four numbers: x,y,width,height") from exc
    if len(region) != 4 or not all(0 <= part <= 1 for part in region):
        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Region must be four fractions between 0 and 1")
    return region


def _project(root, project_id):
    """Open read-mostly: the preview polls these commands, so never rewrite workspace context."""
    from state.project import Project
    from state.workspace import Workspaces
    identifier = project_id or Workspaces(root).active()
    if not identifier:
        raise StudioError(ErrorCode.USER_ACTION_REQUIRED, "Choose or create a project with studio project first")
    return Project.open(root, identifier)


def execute(root, args):
    from presentation.preview import AnnotationQueue, DeckPreview
    project = _project(root, args.project_id)
    if args.action == "preview":
        return DeckPreview(root, project).build(refresh=args.refresh)
    queue = AnnotationQueue(project)
    if args.action == "list":
        return {"project_id": project.path.name, "annotations": queue.list(include_closed=args.all)}
    if args.action == "add":
        if not args.slide:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Annotation requires --slide")
        return queue.add(args.slide, args.object, args.text, region=_region(args.region))
    if args.action in {"done", "dismiss"}:
        if not args.id:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Mark annotations with one or more --id")
        return {"project_id": project.path.name, "annotations": queue.mark(args.id, "done" if args.action == "done" else "dismissed")}
    return _request(root, project, queue)


def _request(root, project, queue):
    """Write the scope file an agent passes to `studio revise --scope` (or live apply)."""
    from ir.validation import validate
    from presentation.backends.ooxml import OOXMLBackend
    from state.io import write_json, logical_path
    if not project.canonical.exists():
        raise StudioError(ErrorCode.USER_ACTION_REQUIRED, "This project has no working deck to revise")
    request = queue.request(OOXMLBackend(root).inspect(project.canonical))
    validate(root, "edit_scope", request["scope"])
    folder = project.path / "work/annotations"
    scope_path = project.policy.check(folder / "scope.json", write=True)
    write_json(scope_path, request["scope"])
    request["scope_path"] = str(logical_path(scope_path))
    request["next_steps"] = [
        "Write a patch_spec JSON that changes only the MAY_CHANGE objects, using their current fingerprints",
        f"studio revise {project.path.name} --patch PATCH.json --scope \"{request['scope_path']}\"",
        f"studio annotate done {project.path.name} " + " ".join("--id " + row["annotation_id"] for row in request["annotations"]),
    ]
    write_json(project.policy.check(folder / "request.json", write=True), request)
    return request
