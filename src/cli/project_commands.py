from state.errors import StudioError, ErrorCode
from state.intake import ProjectIntake
from state.workspace import Workspaces


WORKSPACE_ACTIONS = {None, "list", "use", "files", "import", "start", "others", "quick", "export"}


def execute(root, args):
    if args.action not in WORKSPACE_ACTIONS:
        return _execute_lifecycle(root, args)
    from cli.workspace_menu import ProjectMenu, pick_files
    workspaces = Workspaces(root)
    if args.action is None or args.action == "start":
        return ProjectMenu(root).run(args.project_id)
    if args.action == "others":
        return ProjectMenu(root).run(others=True)
    if args.action == "quick":
        project = workspaces.create_others()
        from state.io import logical_path
        return {"project_id": project.path.name, "category": "others", "path": str(logical_path(project.path)), "workspace": workspaces.metadata(project)}
    if args.action == "list":
        return {"active_project": workspaces.active(), "projects": workspaces.list(args.include_fixtures)}
    project = workspaces.selected(args.project_id)
    if args.action == "export":
        from state.outputs import export_others
        return {"project_id": project.path.name, "export": export_others(root, project.path.name, required=True)}
    if args.action == "use":
        project = workspaces.select(project.path.name)
        return {"project_id": project.path.name, "workspace": workspaces.metadata(project)}
    intake = ProjectIntake(workspaces, project)
    if args.action == "files":
        return {"project_id": project.path.name, "files": intake.files()}
    sources = args.source or pick_files(target=args.role == "target")
    if args.role == "target" and len(sources) != 1:
        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Choose one target PPTX")
    items = intake.import_paths(sources, args.role)
    if args.role == "target":
        intake.initialize_target(items[0])
    return {"project_id": project.path.name, "files": items, "canonical": str(project.canonical)}


def _execute_lifecycle(root, args):
    """Create/open/snapshot/rollback/recover a project by explicit ID."""
    from state.paths import initialize_folders
    from state.project import Project
    if not args.project_id:
        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "This project action requires a project ID")
    initialize_folders(root)
    project = Project.create(root, args.project_id) if args.action == "create" else Project.open(root, args.project_id)
    if args.action == "rollback":
        if not args.snapshot_id:
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Rollback requires --snapshot-id")
        from uuid import uuid4
        from presentation.backends.ooxml import OOXMLBackend
        from presentation.rendering.native import NativeRenderer
        from qa.transaction import PresentationValidator
        validator = PresentationValidator(root, OOXMLBackend(root), NativeRenderer(root), project.path / "work/temp" / ("rollback_render_" + uuid4().hex))
        return project.rollback(args.snapshot_id, project.token(), validator)
    return project.snapshot() if args.action == "snapshot" else project.recover() if args.action == "recover" else project.state()
