from pathlib import Path

from PIL import Image

from references.store import ReferenceStore
from state.io import read_json,native_path,sha256


def cases(root):
    def progressive_native_reference():
        case=read_json(root/"implementation/PHASE_REPORTS/phase_7_native_case.json")
        repository=Path(case["repository"])
        if not repository.resolve().is_relative_to((root/"runtime/pytest").resolve()) or not case["evaluation_isolated"]:raise ValueError("Reference evaluation must remain isolated")
        store=ReferenceStore(repository);ref,slide=case["reference_id"],case["slide_id"]
        metadata=store.load(ref,slide);preview=store.load(ref,slide,"preview");structure=store.load(ref,slide,"structure");original=store.load(ref,slide,"original")
        results=store.query({"text":"Reference ingestion detects a changed native message","content_shape":"text"},limit=100)
        with Image.open(native_path(Path(preview["path"]))) as image:size=image.size
        checks={"source_snapshot_hash":sha256(Path(original["path"]))==original["sha256"],"native_preview":size==(1600,900) and structure["native"]["index"]==1,"observed_metadata":bool(metadata["visual"]["fonts"]) and bool(metadata["visual"]["declared_palette"]),"semantic_retrieval":any(row["reference_id"]==ref and row["slide_id"]==slide for row in results),"approved_separation":metadata["approval"]=="approved" and "approved_internal" in preview["path"] and "approved_internal" in original["path"],"incremental_render":case["incremental_rendered_slides"]==1,"provenance_taint":metadata["trust"]=="untrusted_reference_data" and metadata["provenance"]["source_slide_id"]=="s01"}
        score=100*sum(checks.values())/len(checks)
        return {"passed":all(checks.values()) and score>=90,"score":score,"threshold":90,"checks":checks,"reference_id":ref}
    return [progressive_native_reference]
