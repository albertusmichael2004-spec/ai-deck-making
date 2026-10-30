from pathlib import Path



def add_parser(commands):
    parser=commands.add_parser("design")
    parser.add_argument("project_id")
    parser.add_argument("--request",type=Path,required=True)
    parser.add_argument("--use-project-references",action="store_true",help="Only when this project was selected/named at the start of the prompt")


def execute(root,args):
    from presentation.compiler.design import DesignPlanner
    from state.io import read_json
    from state.project import Project
    project=Project.open(root,args.project_id)
    request=read_json(project.policy.check(args.request))
    if args.use_project_references:request["reference_project"]=project.path.name
    return DesignPlanner(root,project).plan(**request)
