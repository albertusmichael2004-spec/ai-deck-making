"""Read native metrics/export images from a caller-owned PowerPoint presentation."""
from state.io import logical_path


def native_shapes(collection):
    for shape in collection:
        yield shape
        if int(shape.Type)==6:yield from native_shapes(shape.GroupItems)


def text_metrics(shape):
    text=shape.TextFrame2.TextRange;formatted=shape.TextFrame.TextRange
    return {"text":str(text.Text),"text_bounds_pt":{"width":float(text.BoundWidth),"height":float(text.BoundHeight)},"line_count":int(formatted.Lines().Count),"runs":[{"font_pt":float(formatted.Runs(index,1).Font.Size),"font_name":str(formatted.Runs(index,1).Font.Name)} for index in range(1,int(formatted.Runs().Count)+1)],"margins_pt":{"left":float(shape.TextFrame2.MarginLeft),"right":float(shape.TextFrame2.MarginRight),"top":float(shape.TextFrame2.MarginTop),"bottom":float(shape.TextFrame2.MarginBottom)}}


def shape_metrics(shape):
    import pythoncom
    entry={"native_id":int(shape.Id),"name":str(shape.Name),"x_pt":float(shape.Left),"y_pt":float(shape.Top),"width_pt":float(shape.Width),"height_pt":float(shape.Height)}
    try:
        if bool(shape.HasTextFrame) and bool(shape.TextFrame.HasText):
            entry.update(text_metrics(shape));entry["font_pt"]=float(shape.TextFrame2.TextRange.Font.Size)
    except pythoncom.com_error:entry["text_metrics_available"]=False
    try:
        if bool(shape.HasTable):
            entry["table_cells"]=[{"row":row,"column":column,"width_pt":float(shape.Table.Cell(row,column).Shape.Width),"height_pt":float(shape.Table.Cell(row,column).Shape.Height),**text_metrics(shape.Table.Cell(row,column).Shape)} for row in range(1,int(shape.Table.Rows.Count)+1) for column in range(1,int(shape.Table.Columns.Count)+1)]
        if bool(shape.HasChart):
            chart=shape.Chart;entry["chart_series"]=[];collection=chart.SeriesCollection()
            for index in range(1,int(collection.Count)+1):
                series=collection.Item(index)
                measured={"name":str(series.Name),"chart_type":int(series.ChartType),"values":[float(value) for value in series.Values],"categories":[str(value) for value in series.XValues],"labels":[]}
                if int(series.ChartType) in {-4169,72,73,74,75,15,87}:measured["x_values"]=[float(value) for value in series.XValues]
                if int(chart.ChartType)==15:
                    sizes=series.BubbleSizes
                    measured["sizes_formula" if isinstance(sizes,str) else "sizes"]=sizes if isinstance(sizes,str) else [float(value) for value in sizes]
                for point_index in range(1,int(series.Points().Count)+1):
                    point=series.Points(point_index)
                    if bool(point.HasDataLabel):measured["labels"].append({"point_index":point_index-1,"text":str(point.DataLabel.Text),"font_pt":float(point.DataLabel.Font.Size)})
                entry["chart_series"].append(measured)
    except pythoncom.com_error:entry["business_metrics_available"]=False
    return entry


def export_slides(deck,destination,slide_indices=None,progress=None):
    destination.mkdir(parents=True,exist_ok=True);slides=[]
    for index in range(1,int(deck.Slides.Count)+1):
        if slide_indices is not None and index not in slide_indices:continue
        slide=deck.Slides.Item(index);image=destination/f"slide_{index:03}.png"
        if progress:progress(stage="export_slide",slide=index,total=int(deck.Slides.Count))
        if image.exists():raise FileExistsError("Native exporter refuses to overwrite previous renders")
        slide.Export(str(logical_path(image.resolve())),"PNG",1600,900)
        shapes=[]
        for shape in native_shapes(slide.Shapes):
            if progress:progress(stage="shape_metrics",slide=index,total=int(deck.Slides.Count),shape_id=int(shape.Id))
            shapes.append(shape_metrics(shape))
        slides.append({"native_slide_id":int(slide.SlideID),"index":index,"render":str(logical_path(image)),"shapes":shapes})
        if progress:progress(stage="slide_complete",slide=index,total=int(deck.Slides.Count))
    return slides
