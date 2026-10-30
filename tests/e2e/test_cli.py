from pathlib import Path
from uuid import uuid4
import json

from cli.main import main
from presentation.backends.ooxml import OOXMLBackend
from state.io import write_json
from state.project import Project


def test_cli_build_and_scoped_revision_with_real_qa(capsys):
    root=Path(__file__).resolve().parents[2]
    project_id="qa-smoke-"+uuid4().hex[:8]
    assert main(["--root",str(root),"project","create",project_id])==0
    capsys.readouterr()
    assert main(["--root",str(root),"build",project_id,"--spec",str(root/"tests/fixtures/basic_spec.json")])==0
    result=json.loads(capsys.readouterr().out)
    assert result["rendered"] and result["qa"]["passed"]
    assert main(["--root",str(root),"build",project_id,"--spec",str(root/"tests/fixtures/basic_spec.json")])==1
    assert json.loads(capsys.readouterr().out)["code"]=="FILE_CONFLICT"
    project=Project.open(root,project_id);backend=OOXMLBackend(root)
    snapshot=project.snapshot()
    inspection=backend.inspect(project.canonical);slide=inspection["slides"][0];obj=slide["objects"][0]
    job=root/"runtime/cli_tests"/project_id;job.mkdir(parents=True)
    patch={"schema_version":"1.0","patch_id":"cli-test","operations":[{"slide_id":slide["slide_id"],"object_id":obj["object_id"],"operation":"set_text","expected_fingerprint":obj["fingerprint"],"value":"A scoped native revision passes QA"}]}
    scope={"objects":[{"slide_id":s["slide_id"],"object_id":o["object_id"],"protection":"MUST_CHANGE" if o["object_id"]==obj["object_id"] else "MUST_NOT_CHANGE"} for s in inspection["slides"] for o in s["objects"]]}
    write_json(job/"patch.json",patch);write_json(job/"scope.json",scope)
    assert main(["--root",str(root),"revise",project_id,"--patch",str(job/"patch.json"),"--scope",str(job/"scope.json")])==0
    result=json.loads(capsys.readouterr().out)
    assert result["qa"]["passed"] and result["project"]["generation"]==2
    modified=backend.inspect(project.canonical)
    assert modified["slides"][1]==inspection["slides"][1]
    assert modified["slides"][0]["objects"][0]["text"]==patch["operations"][0]["value"]
    assert main(["--root",str(root),"project","rollback",project_id,"--snapshot-id",snapshot])==0
    result=json.loads(capsys.readouterr().out)
    assert result["generation"]==3
    assert backend.inspect(project.canonical)["slides"]==inspection["slides"]
