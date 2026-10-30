from pathlib import Path

from evidence.extraction import extract
from evidence.calculation import calculate,verify_number,validate_units
from state.errors import StudioError,ErrorCode
from state.io import sha256


class EvidenceVerifier:
    """Re-read raw inputs rather than trusting cached displayed/calculated values."""
    def __init__(self,policy):self.policy=policy

    def value(self,graph,identifier):
        node=graph.resolve(identifier)
        if node["status"]!="current":raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Evidence is not current")
        if node["type"]=="raw_fact":
            source=graph.value["sources"][node["source_id"]]
            path=self.policy.check(Path(source["materialized_path"]))
            if sha256(path)!=node["source_sha256"]:raise StudioError(ErrorCode.SOURCE_CONFLICT,"Source hash differs from the evidence version")
            records={record["locator"]:record for record in extract(path)["records"]}
            record=records.get(node["locator"])
            if record is None or record.get("formula") or record["value"]!=node["value"]:
                raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Cached raw evidence differs from independently extracted input")
            return record["value"]
        if node["type"]=="calculated_fact":
            inputs={key:graph.resolve(value) for key,value in node["variables"].items()}
            validate_units(inputs,node["unit"])
            result=calculate(node["formula"],{key:self.value(graph,value) for key,value in node["variables"].items()},{key:value["unit"] for key,value in inputs.items()},node["unit"])
            if not verify_number(node["value"],result):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Cached calculation differs from raw-input recomputation")
            return result
        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Numerical verification requires a raw or calculated fact")

    def displayed(self,graph,identifier,value,tolerance="0"):
        return verify_number(value,self.value(graph,identifier),tolerance)
