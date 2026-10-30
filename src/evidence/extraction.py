import csv
import json
from pathlib import Path

from state.errors import StudioError, ErrorCode
from state.io import native_path


def extract(source: Path):
    """Return typed values and exact locators, never inferred business claims."""
    source = native_path(source)
    extension = source.suffix.lower()
    rows, limitations = [], []
    if extension in {".txt", ".md"}:
        for index, line in enumerate(source.read_text(encoding="utf-8-sig").splitlines(), 1):
            if line.strip(): rows.append({"locator": f"line:{index}", "value": line, "kind": "text"})
    elif extension == ".csv":
        with source.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
                raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "CSV requires unique named columns")
            for index, row in enumerate(reader, 2):
                if None in row or any(value is None for value in row.values()):
                    raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "CSV row width does not match its header")
                for name, value in row.items(): rows.append({"locator": f"row:{index}/column:{name}", "value": value, "kind": "cell", "column": name, "row": index})
    elif extension == ".xlsx":
        from openpyxl import load_workbook
        values, formulas = load_workbook(source, data_only=True, read_only=True), load_workbook(source, data_only=False, read_only=True)
        try:
            for sheet in formulas:
                cached = values[sheet.title]
                for cells,cached_cells in zip(sheet.iter_rows(),cached.iter_rows(),strict=True):
                    for cell,cached_cell in zip(cells,cached_cells,strict=True):
                        if cell.value is None: continue
                        value = cached_cell.value if cell.data_type == "f" else cell.value
                        record = {"locator": f"sheet:{sheet.title}!{cell.coordinate}", "value": value, "kind": "cell", "sheet": sheet.title, "cell": cell.coordinate}
                        if hasattr(value, "isoformat"): record["value"] = value.isoformat()
                        if cell.data_type == "f":
                            record["formula"] = cell.value
                            record["cache_status"] = "unverified_cached" if value is not None else "missing_cached_value"
                            limitations.append({"locator": record["locator"], "reason": "Spreadsheet formula requires explicit recalculation/verification before promotion"})
                        if cell.data_type == "e":
                            record["error"]=cell.value
                            limitations.append({"locator":record["locator"],"reason":"Spreadsheet cell contains an error"})
                        rows.append(record)
        finally:
            values.close(); formulas.close()
    elif extension in {".json", ".jsonl"}:
        text = source.read_text(encoding="utf-8-sig")
        documents = [("$", json.loads(text))] if extension == ".json" else [(f"line:{index}", json.loads(line)) for index, line in enumerate(text.splitlines(), 1) if line.strip()]
        if extension==".json" and isinstance(documents[0][1],dict) and documents[0][1].get("format")=="studio_research_snapshot_v1":
            from research.snapshot import extract_snapshot
            return extract_snapshot(documents[0][1])
        def walk(value, locator):
            if isinstance(value, dict):
                for key, item in value.items(): walk(item, locator + "/" + str(key).replace("~", "~0").replace("/", "~1"))
            elif isinstance(value, list):
                for index, item in enumerate(value): walk(item, locator + "/" + str(index))
            else: rows.append({"locator": locator, "value": value, "kind": "json_value"})
        for locator, document in documents: walk(document, locator)
    elif extension == ".pdf":
        import pymupdf
        with pymupdf.open(stream=source.read_bytes(), filetype="pdf") as document:
            if document.needs_pass:
                raise StudioError(ErrorCode.SOURCE_ACCESS_ERROR, "Encrypted PDF requires authorized decryption")
            for page in document:
                text = page.get_text()
                if text.strip(): rows.append({"locator": f"page:{page.number + 1}", "value": text, "kind": "text"})
                else: limitations.append({"locator": f"page:{page.number + 1}", "reason": "No extractable text; OCR required"})
                for table_index, table in enumerate(page.find_tables().tables):
                    for row_index, cells in enumerate(table.extract()):
                        for column_index, value in enumerate(cells):
                            if value is not None: rows.append({"locator": f"page:{page.number + 1}/table:{table_index}/row:{row_index}/column:{column_index}", "value": value, "kind": "cell"})
    elif extension == ".docx":
        from docx import Document
        document = Document(source)
        for index, paragraph in enumerate(document.paragraphs):
            if paragraph.text.strip(): rows.append({"locator": f"paragraph:{index}", "value": paragraph.text, "kind": "text"})
        for table_index, table in enumerate(document.tables):
            for row_index, row in enumerate(table.rows):
                for column_index, cell in enumerate(row.cells):
                    rows.append({"locator": f"table:{table_index}/row:{row_index}/column:{column_index}", "value": cell.text, "kind": "cell"})
    else:
        raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE, "No data/document extractor for this file type", extension=extension)
    return {"records": rows, "limitations": limitations, "complete": not limitations}
