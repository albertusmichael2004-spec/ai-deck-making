"""Generate native chart/table parts for newly compiled slides only."""
import io
import zipfile
from copy import deepcopy

from pptx import Presentation
from pptx.chart.data import CategoryChartData,XyChartData,BubbleChartData
from pptx.enum.chart import XL_CHART_TYPE,XL_DATA_LABEL_POSITION,XL_LEGEND_POSITION,XL_MARKER_STYLE,XL_TICK_LABEL_POSITION,XL_AXIS_CROSSES
from pptx.util import Inches,Pt
from pptx.dml.color import RGBColor
from pptx.chart.axis import ValueAxis

from ir.identity import numeric_id
from presentation.backends.xml import NS,parse,serialize
from state.errors import StudioError,ErrorCode
from lxml import etree as ET

C={**NS,"c":"http://schemas.openxmlformats.org/drawingml/2006/chart"}


TYPES={"bar":XL_CHART_TYPE.BAR_CLUSTERED,"column":XL_CHART_TYPE.COLUMN_CLUSTERED,"line":XL_CHART_TYPE.LINE_MARKERS,"area":XL_CHART_TYPE.AREA,"pie":XL_CHART_TYPE.PIE,"stacked_bar":XL_CHART_TYPE.BAR_STACKED,"waterfall":XL_CHART_TYPE.COLUMN_STACKED,"bridge":XL_CHART_TYPE.COLUMN_STACKED,"scatter":XL_CHART_TYPE.XY_SCATTER,"bubble":XL_CHART_TYPE.BUBBLE}


from layout.waterfall import waterfall_series


def raw_waterfall_labels(series,index,original,derived,spec):
    c="http://schemas.openxmlformats.org/drawingml/2006/chart";a=NS["a"]
    labels=series.data_labels._element
    for child in list(labels):labels.remove(child)
    if index<2:
        for flag in ["showLegendKey","showVal","showCatName","showSerName","showPercent","showBubbleSize"]:ET.SubElement(labels,f"{{{c}}}"+flag,val="0")
        return
    for point,value in enumerate(derived[index][1]):
        if value==0:continue
        candidates=[candidate for candidate in range(2,7) if derived[candidate][1][point]!=0]
        if index!=candidates[0]:continue
        label=ET.SubElement(labels,f"{{{c}}}dLbl");ET.SubElement(label,f"{{{c}}}idx",val=str(point))
        tx=ET.SubElement(label,f"{{{c}}}tx");rich=ET.SubElement(tx,f"{{{c}}}rich")
        ET.SubElement(rich,f"{{{a}}}bodyPr");ET.SubElement(rich,f"{{{a}}}lstStyle");paragraph=ET.SubElement(rich,f"{{{a}}}p");run=ET.SubElement(paragraph,f"{{{a}}}r")
        props=ET.SubElement(run,f"{{{a}}}rPr",sz=str(round(spec["font_pt"]*100)))
        color=ET.SubElement(props,f"{{{a}}}solidFill");ET.SubElement(color,f"{{{a}}}srgbClr",val="FFFFFF")
        ET.SubElement(props,f"{{{a}}}latin",typeface=spec["font_family"])
        ET.SubElement(run,f"{{{a}}}t").text=spec["series"][0].get("literals",[str(value) for value in original])[point]
        ET.SubElement(label,f"{{{c}}}dLblPos",val="ctr");ET.SubElement(label,f"{{{c}}}showVal",val="0")
    for flag in ["showLegendKey","showVal","showCatName","showSerName","showPercent","showBubbleSize"]:ET.SubElement(labels,f"{{{c}}}"+flag,val="0")


def add_chart(slide,item):
    spec=item["chart"];kind=spec["type"];series=spec["series"]
    if kind in {"scatter","bubble"}:
        data=BubbleChartData() if kind=="bubble" else XyChartData()
        points=data.add_series("Observed relationship")
        for values in zip(*(row["values"] for row in series),strict=True):points.add_data_point(*values)
    else:
        data=CategoryChartData();data.categories=spec["categories"]
        values=waterfall_series(series[0]["values"]) if kind in {"waterfall","bridge"} else [(row["name"],row["values"]) for row in series]
        for name,numbers in values:data.add_series(name,numbers)
    frame=slide.shapes.add_chart(TYPES[kind],*(Inches(item[key]) for key in ["x","y","width","height"]),data)
    chart=frame.chart;chart.has_title=False;chart.has_legend=len(series)>1 and kind not in {"scatter","bubble"}
    if chart.has_legend:chart.legend.position=XL_LEGEND_POSITION.BOTTOM;chart.legend.font.name=spec["font_family"];chart.legend.font.size=Pt(spec["font_pt"])
    axes=[("category_axis",ValueAxis(chart._chartSpace.valAx_lst[0])),("value_axis",ValueAxis(chart._chartSpace.valAx_lst[1]))] if kind in {"scatter","bubble"} else [(name,None) for name in ["category_axis","value_axis"]]
    for axis_name,supplied_axis in axes:
        try:
            axis=supplied_axis if supplied_axis is not None else getattr(chart,axis_name);axis.tick_labels.font.name=spec["font_family"];axis.tick_labels.font.size=Pt(spec["font_pt"]);axis.tick_labels.font.color.rgb=RGBColor.from_string(spec["colors"]["foreground"])
            axis.tick_label_position=XL_TICK_LABEL_POSITION.LOW
            if axis_name=="value_axis" and axis.has_major_gridlines:
                axis.major_gridlines.format.line.color.rgb=RGBColor.from_string(spec["colors"]["grid"]);axis.major_gridlines.format.line.width=Pt(.5)
            if axis_name=="value_axis":axis.tick_labels.number_format=spec["number_format"]
            label=(series[1]["unit"] if axis_name=="value_axis" else series[0]["unit"]) if kind in {"scatter","bubble"} else spec["unit"] if axis_name=="value_axis" else ""
            if label:
                axis.has_title=True;axis.axis_title.text_frame.text=label
                for paragraph in axis.axis_title.text_frame.paragraphs:
                    for run in paragraph.runs:run.font.name=spec["font_family"];run.font.size=Pt(spec["font_pt"]);run.font.color.rgb=RGBColor.from_string(spec["colors"]["foreground"])
        except ValueError:continue
    if kind in {"bar","column","stacked_bar","area","waterfall","bridge"}:
        domain=[number for row in series for number in row["values"]]
        if kind in {"waterfall","bridge"}:
            domain=[series[0]["values"][0]]
            for movement in series[0]["values"][1:-1]:domain.append(domain[-1]+movement)
        chart.value_axis.minimum_scale=0 if min(domain)>=0 else None
    if kind in {"bar","stacked_bar"}:
        chart.category_axis.reverse_order=True;chart.value_axis.crosses=XL_AXIS_CROSSES.AUTOMATIC
        # The category-crossing setting belongs to valAx; the value-crossing setting
        # belongs to catAx. Crossing the value axis at its maximum distorts bar lengths.
        value_crossing=chart.value_axis._element.find("c:crosses",C)
        if value_crossing is not None:value_crossing.set("val","max")
    plot=chart.plots[0]
    if kind not in {"scatter","bubble","area","line"}:
        plot.has_data_labels=True;plot.data_labels.font.name=spec["font_family"];plot.data_labels.font.size=Pt(spec["font_pt"]);plot.data_labels.number_format=spec["number_format"];plot.data_labels.show_value=kind not in {"waterfall","bridge"};plot.data_labels.show_percentage=False
        plot.data_labels.show_category_name=False;plot.data_labels.show_series_name=False;plot.data_labels.show_legend_key=False
        if kind not in {"waterfall","bridge"}:plot.data_labels.position=XL_DATA_LABEL_POSITION.OUTSIDE_END if kind in {"bar","column","pie"} else XL_DATA_LABEL_POSITION.CENTER
        plot.data_labels.font.color.rgb=RGBColor.from_string("FFFFFF" if kind=="stacked_bar" else spec["colors"]["foreground"])
        if kind=="pie":plot.data_labels.show_category_name=True;plot.data_labels.position=XL_DATA_LABEL_POSITION.OUTSIDE_END
    palette=[spec["colors"][key] for key in ["accent","secondary","negative","foreground"]]
    for index,entry in enumerate(chart.series):
        entry.format.fill.solid();entry.format.fill.fore_color.rgb=RGBColor.from_string(palette[index%len(palette)])
        entry.format.line.color.rgb=RGBColor.from_string(palette[index%len(palette)])
        if kind in {"bar","column","stacked_bar","waterfall","bridge"}:entry.invert_if_negative=False
        if kind=="scatter":
            entry.format.line.fill.background();entry.marker.style=XL_MARKER_STYLE.CIRCLE;entry.marker.size=6
            entry.marker.format.fill.solid();entry.marker.format.fill.fore_color.rgb=RGBColor.from_string(spec["colors"]["accent"])
            entry.marker.format.line.color.rgb=RGBColor.from_string(spec["colors"]["accent"])
        if kind=="pie":
            for point_index,point in enumerate(entry.points):
                point.format.fill.solid();point.format.fill.fore_color.rgb=RGBColor.from_string(palette[point_index%len(palette)])
        if kind in {"waterfall","bridge"}:
            color=spec["colors"]["negative"] if index in {4,5} else spec["colors"]["accent"] if index in {2,3} else spec["colors"]["foreground"]
            entry.format.fill.fore_color.rgb=RGBColor.from_string(color);entry.format.line.color.rgb=RGBColor.from_string(color)
            if index<2:entry.format.fill.background();entry.format.line.fill.background()
            raw_waterfall_labels(entry,index,series[0]["values"],values,spec)
    # All textual chart defaults are explicit rather than inherited from vendor themes.
    chart._chartSpace.get_or_add_txPr().bodyPr  # ensure native default text properties exist
    return frame


def add_table(slide,item):
    spec=item["table"];rows=[spec["headers"],*spec["rows"]]
    frame=slide.shapes.add_table(len(rows),len(spec["headers"]),*(Inches(item[key]) for key in ["x","y","width","height"]))
    table=frame.table
    for row_index,row in enumerate(rows):
        for column,text in enumerate(row):
            cell=table.cell(row_index,column);cell.text=str(text)
            cell.margin_left=cell.margin_right=Inches(.08);cell.margin_top=cell.margin_bottom=Inches(.025)
            cell.fill.solid();cell.fill.fore_color.rgb=RGBColor.from_string(spec["colors"]["accent"] if row_index==0 else spec["colors"]["background"])
            for paragraph in cell.text_frame.paragraphs:
                for run in paragraph.runs:
                    run.font.name=spec["font_family"];run.font.size=Pt(spec["font_pt"]);run.font.bold=row_index==0;run.font.color.rgb=RGBColor.from_string("FFFFFF" if row_index==0 else spec["colors"]["foreground"])
    return frame


def augment(package,compiled):
    original=io.BytesIO()
    with zipfile.ZipFile(original,"w") as archive:
        for name,(_,data) in package.items():archive.writestr(name,data)
    deck=Presentation(io.BytesIO(original.getvalue()))
    for slide,spec in zip(deck.slides,compiled,strict=True):
        seen={int(shape.shape_id) for shape in slide.shapes}
        for item in spec["objects"]:
            if item["kind"] not in {"chart","table"}:continue
            number=numeric_id(item["object_id"])
            if number in seen:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Exhibit object identity collision")
            seen.add(number)
            frame=add_chart(slide,item) if item["kind"]=="chart" else add_table(slide,item)
            properties=frame._element.find(".//p:cNvPr",NS);properties.set("id",str(number));properties.set("name","studio:"+item["object_id"]);properties.set("descr","studio-role:exhibit")
    saved=io.BytesIO();deck.save(saved)
    with zipfile.ZipFile(saved) as archive:generated={info.filename:(info,archive.read(info)) for info in archive.infolist()}
    generated_slides=[str(slide.part.partname).lstrip("/") for slide in deck.slides]
    def relation_name(name):return "ppt/slides/_rels/"+name.split("/")[-1]+".rels"
    renamed={name for slide_name in generated_slides for name in [slide_name,relation_name(slide_name)]}
    new_names=set(generated)-set(package)-renamed
    for name in new_names:package[name]=generated[name]
    # Preserve original masters/layouts/themes byte-for-byte; copy only new frames and relationships.
    for index,spec in enumerate(compiled):
        name="ppt/slides/studio_"+spec["slide_id"]+".xml";node=parse(package[name][1]);augmented=parse(generated[generated_slides[index]][1]);tree=node.find("p:cSld/p:spTree",NS)
        identities={"studio:"+item["object_id"] for item in spec["objects"] if item["kind"] in {"chart","table"}}
        for frame in augmented.findall("p:cSld/p:spTree/p:graphicFrame",NS):
            if frame.find(".//p:cNvPr",NS).get("name") in identities:tree.append(deepcopy(frame))
        package[name]=(package[name][0],serialize(node))
        relation="ppt/slides/_rels/studio_"+spec["slide_id"]+".xml.rels";node=parse(package[relation][1]);existing={row.get("Id"):dict(row.attrib) for row in node}
        for row in parse(generated[relation_name(generated_slides[index])][1]):
            if row.get("Id") in existing:
                if dict(row.attrib)!=existing[row.get("Id")]:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Exhibit generation changed an existing relationship")
            else:node.append(deepcopy(row))
        package[relation]=(package[relation][0],serialize(node))
    node=parse(package["[Content_Types].xml"][1]);existing={(row.tag,row.get("PartName",row.get("Extension"))) for row in node}
    for row in parse(generated["[Content_Types].xml"][1]):
        key=(row.tag,row.get("PartName",row.get("Extension")))
        if key not in existing and (not row.get("PartName") or row.get("PartName").lstrip("/") in package):node.append(deepcopy(row));existing.add(key)
    package["[Content_Types].xml"]=(package["[Content_Types].xml"][0],serialize(node))
    return package
