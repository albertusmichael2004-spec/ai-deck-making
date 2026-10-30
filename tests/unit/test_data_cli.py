import json

from cli.main import main
from state.io import write_json


def test_manual_data_ingest_calculate_trace_and_numeric_verify(repo,capsys):
    assert main(["--root",str(repo),"project","create","data-test"])==0
    capsys.readouterr()
    source=repo/"data.csv";source.write_text("revenue,cost\n100,60\n",encoding="utf-8")
    metadata=repo/"source_metadata.json"
    write_json(metadata,{"schema_version":"1.0","units":{"default":{"label":"currency","currency":"IDR"}},"data_period":"2025"})
    assert main(["--root",str(repo),"data","ingest","data-test","--source",str(source),"--request",str(metadata)])==0
    ingestion=json.loads(capsys.readouterr().out)
    request=repo/"calculation.json"
    write_json(request,{"schema_version":"1.0","calculation_id":"profit","formula":"revenue-cost","inputs":{"revenue":ingestion["evidence_ids"][0],"cost":ingestion["evidence_ids"][1]},"unit":{"label":"currency","currency":"IDR"}})
    assert main(["--root",str(repo),"data","calculate","data-test","--request",str(request)])==0
    capsys.readouterr()
    assert main(["--root",str(repo),"data","verify","data-test","--evidence-id","profit","--displayed","40"])==0
    assert json.loads(capsys.readouterr().out)["passed"]
    assert main(["--root",str(repo),"data","verify","data-test","--evidence-id","profit","--displayed","41"])==1
    assert not json.loads(capsys.readouterr().out)["passed"]
