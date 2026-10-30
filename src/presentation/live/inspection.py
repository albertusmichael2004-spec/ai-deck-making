import hashlib
import json
from datetime import datetime,timezone

from presentation.rendering.metrics import native_shapes,shape_metrics
from state.errors import StudioError,ErrorCode


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()
def slide_identity(slide):
    name=str(slide.Name)
    return name[7:] if name.startswith("studio:") else "slide-"+str(int(slide.SlideID))
def object_identity(shape):
    name=str(shape.Name)
    return name[7:] if name.startswith("studio:") else "shape-"+str(int(shape.Id))


def shape_state(shape):
    row=shape_metrics(shape);row.update(object_id=object_identity(shape),kind=int(shape.Type))
    description=str(shape.AlternativeText)
    row["role"]=description[12:] if description.startswith("studio-role:") else None
    row["font_runs"]=[]
    if bool(shape.HasTextFrame) and bool(shape.TextFrame.HasText):
        text=shape.TextFrame.TextRange
        row["font_runs"]=[{"text":str(text.Runs(i,1).Text),"name":str(text.Runs(i,1).Font.Name),"size":float(text.Runs(i,1).Font.Size),"bold":int(text.Runs(i,1).Font.Bold),"italic":int(text.Runs(i,1).Font.Italic),"color":int(text.Runs(i,1).Font.Color.RGB)} for i in range(1,int(text.Runs().Count)+1)]
    try:row["fill"]={"type":int(shape.Fill.Type),"visible":int(shape.Fill.Visible),"color":int(shape.Fill.ForeColor.RGB),"transparency":float(shape.Fill.Transparency)}
    except Exception:row["fill"]=None
    if bool(shape.HasChart):
        row["chart_axes"]=[]
        for kind in [1,2]:
            try:
                axis=shape.Chart.Axes(kind,1)
                row["chart_axes"].append({"kind":kind,"crosses":int(axis.Crosses),"reverse":bool(axis.ReversePlotOrder),"minimum":float(axis.MinimumScale) if kind==2 else None,"maximum":float(axis.MaximumScale) if kind==2 else None})
            except Exception:continue
    if bool(shape.HasTable):
        row["table_selected_cells"]=[{"row":r,"column":c} for r in range(1,int(shape.Table.Rows.Count)+1) for c in range(1,int(shape.Table.Columns.Count)+1) if bool(shape.Table.Cell(r,c).Selected)]
    # Selection is captured separately; it must not make a content fingerprint unstable.
    content={key:value for key,value in row.items() if key!="table_selected_cells"}
    row["fingerprint"]=digest(content)
    return row


def inspect_deck(deck):
    slides=[]
    for index in range(1,int(deck.Slides.Count)+1):
        slide=deck.Slides.Item(index)
        slides.append({"slide_id":slide_identity(slide),"native_slide_id":int(slide.SlideID),"index":index,"objects":[shape_state(shape) for shape in native_shapes(slide.Shapes)]})
    value={"canvas_pt":{"width":float(deck.PageSetup.SlideWidth),"height":float(deck.PageSetup.SlideHeight)},"slides":slides}
    content={**value,"slides":[{**slide,"objects":[{key:value for key,value in obj.items() if key!="table_selected_cells"} for obj in slide["objects"]]} for slide in slides]}
    return {**value,"fingerprint":digest(content),"saved":bool(deck.Saved),"full_name":str(deck.FullName),"name":str(deck.Name)}


def selection_context(app,deck,inspection,generation):
    try:
        window=app.ActiveWindow
        if str(window.Presentation.FullName).casefold()!=str(deck.FullName).casefold():raise StudioError(ErrorCode.LIVE_SELECTION_STALE,"Active window belongs to another presentation")
        selection=window.Selection;kind=int(selection.Type)
        context={"schema_version":"1.0","captured_at":now(),"presentation_id":digest(str(deck.FullName).casefold()),"generation_id":generation,"selection_type":{0:"none",1:"slide_range",2:"shape_range",3:"text"}.get(kind,"none"),"slide_ids":[],"objects":[],"text_scope":None,"active_slide_id":slide_identity(window.View.Slide)}
        selected=[]
        if kind==1:context["slide_ids"]=[slide_identity(slide) for slide in selection.SlideRange]
        elif kind in {2,3}:
            selected=list(selection.ChildShapeRange if bool(selection.HasChildShapeRange) else selection.ShapeRange)
            context["slide_ids"]=[context["active_slide_id"]]
        for slide in inspection["slides"]:
            for obj in slide["objects"]:
                if slide["slide_id"] in context["slide_ids"] and (kind==1 or any(int(shape.Id)==obj["native_id"] for shape in selected)):
                    context["objects"].append({"slide_id":slide["slide_id"],"object_id":obj["object_id"],"native_id":obj["native_id"],"fingerprint":obj["fingerprint"],"content_type":"chart" if "chart_series" in obj else "table" if "table_cells" in obj else "text" if obj.get("text") else "shape","table_cells":obj.get("table_selected_cells",[])})
        if kind==3:
            text=selection.TextRange
            context["text_scope"]={"start":int(text.Start),"length":int(text.Length),"text":str(text.Text)}
        return context
    except StudioError:raise
    except Exception as exc:raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE,"Active selection is unavailable; no scope was guessed") from exc


def comments(deck):
    rows=[];capabilities={"comments_read":True,"replies_read":False}
    for slide in deck.Slides:
        try:collection=slide.Comments
        except Exception:
            capabilities["comments_read"]=False;continue
        for comment in collection:
            row={"slide_id":slide_identity(slide),"author":str(comment.Author),"created_at":comment.DateTime.isoformat(),"text":str(comment.Text),"anchor":{"left_pt":float(comment.Left),"top_pt":float(comment.Top)},"replies":[]}
            try:
                row["replies"]=[{"author":str(reply.Author),"created_at":reply.DateTime.isoformat(),"text":str(reply.Text)} for reply in comment.Replies]
                capabilities["replies_read"]=True
            except Exception:pass
            row["annotation_id"]="ann_"+digest(row)
            rows.append(row)
    return rows,capabilities
