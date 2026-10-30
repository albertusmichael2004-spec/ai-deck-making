"""Generate the bounded style patch contract (no changes to older versions)."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
def obj(properties):
    return {"type":"object", "additionalProperties":False, "required":list(properties), "properties":properties}
color = {"type":"string", "pattern":"^[a-fA-F0-9]{6}$"}
index = {"type":"integer", "minimum":0}
geometry = obj({k:{"type":"number", **({"exclusiveMinimum":0} if k in {"width","height"} else {})} for k in ["x","y","width","height"]})
values = {
    "set_text":{"type":"string"}, "set_fill":color, "set_geometry":geometry,
    "repair_chart_axis":{"type":"string", "const":"zero_origin"},
    "connector_to_shape":obj({"geometry":geometry}),
    "set_gradient_fill":obj({"angle_deg":{"type":"number","minimum":0,"exclusiveMaximum":360}, "stops":{"type":"array","minItems":2,"maxItems":10,"items":obj({"position":{"type":"number","minimum":0,"maximum":1},"color":color})}}),
    "set_chart_colors":obj({"series":{"type":"array","minItems":1,"maxItems":256,"items":obj({"index":index,"color":{"anyOf":[color,{"type":"null"}]},"points":{"type":"array","maxItems":10000,"items":obj({"index":index,"color":color})}})}}),
}
variants = []
for name, value in values.items():
    variants.append(obj({"slide_id":{"type":"string","minLength":1},"object_id":{"type":"string","minLength":1},"operation":{"type":"string","const":name},"expected_fingerprint":{"type":"string","pattern":"^[a-f0-9]{64}$"},"value":value}))
schema = {"$schema":"https://json-schema.org/draft/2020-12/schema", **obj({"schema_version":{"type":"string","const":"1.2"},"patch_id":{"type":"string","minLength":1},"operations":{"type":"array","minItems":1,"items":{"anyOf":variants}}})}
(root/"schemas/patch_spec/1.2.json").write_text(json.dumps(schema,indent=2)+"\n",encoding="utf-8")
plan = json.loads((root/"schemas/patch_plan/1.0.json").read_text())
plan["properties"]["schema_version"] = {"type":"string","const":"1.1"}
plan["properties"]["patch"]["anyOf"].append({"$ref":"../patch_spec/1.2.json"})
(root/"schemas/patch_plan/1.1.json").write_text(json.dumps(plan,indent=2)+"\n",encoding="utf-8")
