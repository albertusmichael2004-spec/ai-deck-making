import io
import posixpath
import re
from decimal import Decimal

from openpyxl import load_workbook
from openpyxl.utils import range_boundaries
from presentation.backends.xml import NS,parse
from state.errors import StudioError,ErrorCode


C={**NS,"c":"http://schemas.openxmlformats.org/drawingml/2006/chart"}


def point_values(cache,convert=float):
    if cache is None:return []
    return [convert(point.find("c:v",C).text) if point.find("c:v",C) is not None else None for point in sorted(cache.findall("c:pt",C),key=lambda row:int(row.get("idx")))]


def inspect_business(shape,slide_part,package):
    table=shape.find(".//a:tbl",NS)
    if table is not None:
        return {"content_type":"table","table_data":[["\n".join("".join(paragraph.itertext()) for paragraph in cell.findall("a:txBody/a:p",NS)) for cell in row.findall("a:tc",NS)] for row in table.findall("a:tr",NS)]}
    chart_ref=shape.find(".//c:chart",C)
    if chart_ref is None:return {"content_type":"shape"}
    relations=posixpath.join(posixpath.dirname(slide_part),"_rels",posixpath.basename(slide_part)+".rels")
    relation=next((row for row in parse(package[relations][1]) if row.get("Id")==chart_ref.get(f"{{{NS['r']}}}id")),None)
    if relation is None or relation.get("TargetMode")=="External":raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Native chart relationship is unresolved")
    chart_part=posixpath.normpath(posixpath.join(posixpath.dirname(slide_part),relation.get("Target")))
    if chart_part not in package:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Native chart part is absent")
    chart=parse(package[chart_part][1]);series=[]
    for row in chart.findall(".//c:ser",C):
        cache=row.find("c:val/c:numRef/c:numCache",C)
        if cache is None:cache=row.find("c:yVal/c:numRef/c:numCache",C)
        series.append({"values":point_values(cache),"x_values":point_values(row.find("c:xVal/c:numRef/c:numCache",C)),"custom_labels":{int(label.find("c:idx",C).get("val")):"".join(label.findall("c:tx/c:rich//a:t",C)[0].itertext()) for label in row.findall("c:dLbls/c:dLbl",C) if label.find("c:tx/c:rich//a:t",C) is not None}})
    for result,row in zip(series,chart.findall(".//c:ser",C),strict=True):
        result["categories"]=point_values(row.find("c:cat/c:strRef/c:strCache",C),str)
    workbook_cells={}
    rel_path=posixpath.join(posixpath.dirname(chart_part),"_rels",posixpath.basename(chart_part)+".rels")
    if rel_path in package:
        for row in parse(package[rel_path][1]):
            if row.get("Type","").endswith("/package"):
                target=posixpath.normpath(posixpath.join(posixpath.dirname(chart_part),row.get("Target")))
                if target not in package:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Native chart workbook is absent")
                book=load_workbook(io.BytesIO(package[target][1]),data_only=False,read_only=True)
                try:
                    for formula in chart.findall(".//c:f",C):
                        text=formula.text or ""
                        if "!" not in text:continue
                        sheet_name,reference=text.rsplit("!",1);sheet_name=sheet_name.strip("'").replace("''","'")
                        if not re.fullmatch(r"\$?[A-Z]+\$?[1-9][0-9]*(?::\$?[A-Z]+\$?[1-9][0-9]*)?",reference) or sheet_name not in book.sheetnames:continue
                        min_col,min_row,max_col,max_row=range_boundaries(reference)
                        if (max_row-min_row+1)*(max_col-min_col+1)>20000:continue
                        sheet=book[sheet_name]
                        for cells in sheet.iter_rows(min_row=min_row,max_row=max_row,min_col=min_col,max_col=max_col):
                            for cell in cells:
                                value=cell.value
                                if hasattr(value,"isoformat"):value=value.isoformat()
                                if value is not None:workbook_cells[sheet.title+"!"+cell.coordinate]=value
                finally:book.close()
    for result,row in zip(series,chart.findall(".//c:ser",C),strict=True):
        for key,path in [("workbook_values","c:val/c:numRef/c:f"),("workbook_x","c:xVal/c:numRef/c:f"),("workbook_y","c:yVal/c:numRef/c:f"),("workbook_sizes","c:bubbleSize/c:numRef/c:f"),("workbook_categories","c:cat/c:strRef/c:f")]:
            formula=row.find(path,C);values=[]
            if formula is not None and "!" in (formula.text or ""):
                sheet_name,reference=formula.text.rsplit("!",1);sheet_name=sheet_name.strip("'").replace("''","'")
                if re.fullmatch(r"\$?[A-Z]+\$?[1-9][0-9]*(?::\$?[A-Z]+\$?[1-9][0-9]*)?",reference):
                    min_col,min_row,max_col,max_row=range_boundaries(reference)
                    if (max_row-min_row+1)*(max_col-min_col+1)<=20000:
                        from openpyxl.utils import get_column_letter
                        values=[workbook_cells.get(sheet_name+"!"+get_column_letter(column)+str(index)) for index in range(min_row,max_row+1) for column in range(min_col,max_col+1)]
            result[key]=values
        result["sizes"]=point_values(row.find("c:bubbleSize/c:numRef/c:numCache",C))
        formula=row.find("c:bubbleSize/c:numRef/c:f",C)
        result["sizes_formula"]=formula.text if formula is not None else None
    axes=[]
    for tag in ["catAx","valAx"]:
        for axis in chart.findall(".//c:"+tag,C):
            row={"kind":tag}
            for key,path in [("crosses","c:crosses"),("crosses_at","c:crossesAt"),("minimum","c:scaling/c:min"),("maximum","c:scaling/c:max"),("orientation","c:scaling/c:orientation")]:
                node=axis.find(path,C);row[key]=node.get("val") if node is not None else None
            axes.append(row)
    return {"content_type":"chart","chart_part":chart_part,"chart_data":series,"chart_axes":axes,"workbook_cells":workbook_cells}
