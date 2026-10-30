from pathlib import Path
import json

from knowledge.bootstrap import verify_bootstrap


def test_bootstrap_inventory_migration_and_idempotency():
    root = Path(__file__).resolve().parents[2]
    first, second = verify_bootstrap(root), verify_bootstrap(root)
    assert first == second
    assert first["passed"], first["errors"]
    assert first["original_files"] == 1124
    assert first["local_links"] == 239
    assert not first["archive_ingestion"]
    inventory = json.loads((root / "library/knowledge/packages/consulting_deck_knowledge_v1/bootstrap_inventory.json").read_text(encoding="utf-8"))
    roles = {row["role"] for row in inventory["files"]}
    assert {"evaluation_isolated", "machine_contract", "inert_production_tooling", "archive_backup", "structured_knowledge_chunks"} <= roles
    assert len(inventory["top_level"]) == 11
