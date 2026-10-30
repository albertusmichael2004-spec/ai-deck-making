from state.errors import StudioError, ErrorCode
from state.intake import ProjectIntake
from state.workspace import Workspaces


def execute(root, args):
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
