from ir.identity import object_id
from state.io import read_yaml
from state.errors import StudioError, ErrorCode


class BaselineLayout:
    def __init__(self, repository):
        self.tokens = read_yaml(repository / "config/layout_rules/baseline.yaml")

    def compile(self, deck: dict, slide: dict, source_notes=()) -> dict:
        if slide["exhibit"]["type"] not in {"text","shapes"} or slide["brand_profile"]!="default_consulting":raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE,"Baseline layout cannot represent this exhibit or brand")
        canvas = deck["canvas"]
        if slide.get("objects"):
            objects = [dict(item) for item in slide["objects"]]
        else:
            margin = self.tokens["margin_in"]
            width = canvas["width_in"] - margin * 2
            body = "\n".join([slide["key_message"], *slide.get("insights", [])])
            objects = [
                {"object_id": object_id(deck["deck_id"], slide["slide_id"], "title"), "kind": "text", "role": "title", "text": slide["action_title"], "x": margin, "y": margin, "width": width, "height": self.tokens["title_height_in"], "font_pt": self.tokens["title_font_pt"], "bold": True, "color": self.tokens["foreground"], "protection": "MAY_CHANGE"},
                {"object_id": object_id(deck["deck_id"], slide["slide_id"], "message"), "kind": "text", "role": "body", "text": body, "x": margin, "y": self.tokens["body_y_in"], "width": width, "height": canvas["height_in"] - self.tokens["body_y_in"] - margin, "font_pt": self.tokens["body_font_pt"], "bold": False, "color": self.tokens["foreground"], "protection": "MAY_CHANGE"},
            ]
        if source_notes:
            source_y=canvas["height_in"]-.7
            for item in objects:
                if item.get("role")=="body":item["height"]=min(item["height"],source_y-item["y"]-.2)
            objects.append({"object_id":object_id(deck["deck_id"],slide["slide_id"],"source"),"kind":"text","role":"source","text":"; ".join(source_notes),"x":self.tokens["margin_in"],"y":source_y,"width":canvas["width_in"]-2*self.tokens["margin_in"],"height":.4,"font_pt":12,"color":self.tokens["foreground"],"protection":"MUST_NOT_CHANGE"})
        identifiers = [item["object_id"] for item in objects]
        if len(identifiers) != len(set(identifiers)):
            raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Duplicate object identities")
        return {"slide_id": slide["slide_id"], "objects": objects, "background": self.tokens["background"]}
