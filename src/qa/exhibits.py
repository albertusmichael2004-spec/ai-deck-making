from decimal import Decimal

from evidence.exhibits import CHARTS
from layout.waterfall import waterfall_series
from qa.severity import issue,Severity


def data_exhibits(slides,evidence,inspection,rendered):
    findings=[]
    for expected,actual,native in zip(slides,inspection["slides"],rendered["slides"],strict=True):
        footers=" ".join(" ".join(obj.get("text","").split()) for obj in actual["objects"] if obj.get("role")=="source" or obj.get("text","").lstrip().lower().startswith("source:"))
        for source_id in expected.get("source_note_ids",[]):
            note=" ".join(evidence.source_note(source_id).split())
            if note not in footers:findings.append(issue("SOURCE_CITATION_MISSING",Severity.BLOCKER,actual["slide_id"],None,"Visible source attribution does not cover the registered source"))
        kind=expected["exhibit"]["type"]
        if kind not in CHARTS|{"table","matrix"}:continue
        payload=evidence.resolve_exhibit(expected)
        frames=[obj for obj in actual["objects"] if obj.get("content_type") in {"chart","table"}]
        if len(frames)!=1:
            findings.append(issue("EXHIBIT_PROOF_MISSING",Severity.BLOCKER,actual["slide_id"],None,"One bound native exhibit is required"));continue
        frame=frames[0]
        if kind in {"table","matrix"}:
            if frame["table_data"]!=[payload["headers"],*payload["resolved_rows"]]:findings.append(issue("TABLE_SOURCE_MISMATCH",Severity.BLOCKER,actual["slide_id"],frame["object_id"],"Native table values differ from independently read evidence"))
            continue
        series=payload["resolved_series"]
        if kind in {"bar","stacked_bar"}:
            category_axes=[row for row in frame.get("chart_axes",[]) if row["kind"]=="catAx"]
            value_axes=[row for row in frame.get("chart_axes",[]) if row["kind"]=="valAx"]
            invalid=not category_axes or not value_axes
            invalid=invalid or any(row["crosses"] not in {None,"autoZero"} and not (row["crosses"] is None and row["crosses_at"] is not None and Decimal(row["crosses_at"])==0) for row in category_axes)
            invalid=invalid or any(row["crosses_at"] is not None and Decimal(row["crosses_at"])!=0 for row in category_axes)
            invalid=invalid or any(row["minimum"] is not None and Decimal(row["minimum"])>0 for row in value_axes)
            if invalid:findings.append(issue("CHART_ORIGIN_NOT_ZERO",Severity.BLOCKER,actual["slide_id"],frame["object_id"],"Native horizontal bar origin must remain zero; labels alone cannot prove truthful bar lengths"))
        expected_values=[values for name,values in waterfall_series(series[0]["values"])] if kind in {"waterfall","bridge"} else [series[1]["values"]] if kind in {"scatter","bubble"} else [row["values"] for row in series]
        native_frame=next((row for row in native["shapes"] if str(row["native_id"])==frame["native_id"]),{})
        observed=[row["values"] for row in frame["chart_data"]]
        native_values=[row["values"] for row in native_frame.get("chart_series",[])]
        if expected_values!=observed or expected_values!=native_values:findings.append(issue("CHART_SOURCE_MISMATCH",Severity.BLOCKER,actual["slide_id"],frame["object_id"],"Native/cache chart values differ from bound evidence"))
        if kind not in {"scatter","bubble"}:
            if any(row["categories"]!=payload["resolved_categories"] for row in frame["chart_data"]) or any(row.get("categories")!=payload["resolved_categories"] for row in native_frame.get("chart_series",[])):findings.append(issue("CHART_CATEGORY_MISMATCH",Severity.BLOCKER,actual["slide_id"],frame["object_id"],"Native/cache categories differ from bound source labels"))
            if any([str(value) for value in row["workbook_categories"]]!=payload["resolved_categories"] for row in frame["chart_data"]):findings.append(issue("CHART_WORKBOOK_CATEGORY_MISMATCH",Severity.BLOCKER,actual["slide_id"],frame["object_id"],"Editable workbook categories differ from bound source labels"))
        elif frame["chart_data"][0]["x_values"]!=series[0]["values"] or native_frame.get("chart_series",[{}])[0].get("x_values")!=series[0]["values"]:findings.append(issue("CHART_X_SOURCE_MISMATCH",Severity.BLOCKER,actual["slide_id"],frame["object_id"],"Association x coordinates differ from bound evidence"))
        if kind in {"waterfall","bridge"}:
            labels={point:text for row in frame["chart_data"] for point,text in row["custom_labels"].items()}
            if any(labels.get(index)!=literal for index,literal in enumerate(series[0]["literals"]) if Decimal(literal)!=0):findings.append(issue("BRIDGE_LABEL_MISMATCH",Severity.BLOCKER,actual["slide_id"],frame["object_id"],"Bridge labels differ from original source movements/endpoints"))
            visible={label["point_index"]:label["text"] for row in native_frame.get("chart_series",[]) for label in row.get("labels",[]) if label["text"].strip()}
            if any(visible.get(index)!=literal for index,literal in enumerate(series[0]["literals"]) if Decimal(literal)!=0) or any(index not in range(len(series[0]["literals"])) for index in visible):findings.append(issue("NATIVE_BRIDGE_LABEL_MISMATCH",Severity.BLOCKER,actual["slide_id"],frame["object_id"],"Rendered bridge label text differs from source movements/endpoints"))
        for row in native_frame.get("chart_series",[]):
            if any(label["text"].strip() and label["font_pt"]<12 for label in row.get("labels",[])):findings.append(issue("CHART_LABEL_FONT_TOO_SMALL",Severity.MAJOR,actual["slide_id"],frame["object_id"],"Native data label is below the readable minimum"))
        workbook_values=[row["workbook_y"] if kind in {"scatter","bubble"} else row["workbook_values"] for row in frame["chart_data"]]
        if workbook_values!=expected_values:findings.append(issue("CHART_WORKBOOK_MISMATCH",Severity.BLOCKER,actual["slide_id"],frame["object_id"],"Editable workbook differs from bound chart values"))
        if kind in {"scatter","bubble"} and frame["chart_data"][0]["workbook_x"]!=series[0]["values"]:findings.append(issue("CHART_WORKBOOK_X_MISMATCH",Severity.BLOCKER,actual["slide_id"],frame["object_id"],"Editable workbook x coordinates differ from bound values"))
        if kind=="bubble":
            sizes=native_frame.get("chart_series",[{}])[0]
            # Office exposes either numeric sizes or the actual native workbook range.
            native_matches=sizes.get("sizes")==series[2]["values"] or bool(sizes.get("sizes_formula")) and sizes["sizes_formula"].lstrip("=")==frame["chart_data"][0].get("sizes_formula")
            if frame["chart_data"][0]["sizes"]!=series[2]["values"] or frame["chart_data"][0]["workbook_sizes"]!=series[2]["values"] or not native_matches:findings.append(issue("CHART_BUBBLE_SIZE_MISMATCH",Severity.BLOCKER,actual["slide_id"],frame["object_id"],"Native/cache/workbook bubble sizes differ from bound evidence"))
    return findings
