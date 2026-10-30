from decimal import Decimal,InvalidOperation,Context,localcontext
from evidence.calculation import CALCULATION_PRECISION
from copy import deepcopy

from evidence.verification import EvidenceVerifier
from state.errors import StudioError,ErrorCode
from evidence.association import verify_association


CHARTS={"bar","column","line","area","pie","stacked_bar","scatter","bubble","waterfall","bridge"}


class ExhibitResolver:
    def __init__(self,graph,policy):self.graph,self.verifier=graph,EvidenceVerifier(policy)

    def resolve(self,slide):
        with localcontext(Context(prec=CALCULATION_PRECISION)):return self._resolve(slide)

    def _resolve(self,slide):
        exhibit=deepcopy(slide["exhibit"]);kind=exhibit["type"]
        if kind not in CHARTS|{"table","matrix"}:return exhibit
        binding=self.graph.value["bindings"].get(exhibit.get("binding_id"))
        if not binding or binding["slide_id"]!=slide["slide_id"]:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Exhibit requires a registered slide-specific data binding")
        used=[]
        def value(identifier,numeric=False,unit_label=None):
            if identifier not in binding["evidence_ids"]:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Exhibit references evidence outside its binding")
            node=self.graph.resolve(identifier);actual=self.verifier.value(self.graph,identifier);used.append(identifier)
            if not numeric:return str(actual)
            try:number=Decimal(str(actual))
            except InvalidOperation as exc:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Chart cell is not numeric") from exc
            if not number.is_finite() or len(number.normalize().as_tuple().digits)>15:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Chart requires finite values within native workbook precision")
            expected=unit_label or exhibit.get("unit")
            if not expected or node.get("unit",{}).get("label")!=expected:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Chart units differ from bound evidence")
            if exhibit.get("period"):
                periods={item.get("freshness",{}).get("data_period") for item in self.graph.trace(identifier) if item["type"]=="raw_fact"}
                if periods!={exhibit["period"]}:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Chart period differs from bound evidence")
            return float(number)
        if kind in {"table","matrix"}:
            exhibit["resolved_rows"]=[[value(identifier) for identifier in row] for row in exhibit["rows"]]
            if any(len(row)!=len(exhibit["headers"]) for row in exhibit["resolved_rows"]):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Table rows differ from header width")
        else:
            exhibit["resolved_categories"]=[value(identifier) for identifier in exhibit["category_evidence_ids"]]
            for series in exhibit["series"]:
                if len(series["evidence_ids"])!=len(exhibit["category_evidence_ids"]):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Chart category/series dimensions differ")
                for category,quantity in zip(exhibit["category_evidence_ids"],series["evidence_ids"],strict=True):verify_association(self.graph,category,quantity)
            exhibit["resolved_series"]=[{"name":series["name"],"unit":series.get("unit",exhibit.get("unit")),"literals":[str(self.verifier.value(self.graph,identifier)) for identifier in series["evidence_ids"]],"values":[value(identifier,True,series.get("unit")) for identifier in series["evidence_ids"]]} for series in exhibit["series"]]
            if any(len(row["values"])!=len(exhibit["resolved_categories"]) for row in exhibit["resolved_series"]):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Chart category/series dimensions differ")
            if kind in {"pie","waterfall","bridge"} and len(exhibit["resolved_series"])!=1:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Exhibit requires one comparable value series")
            if kind=="pie" and any(number<0 for number in exhibit["resolved_series"][0]["values"]):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Composition pie cannot contain negative values")
            if kind in {"scatter","bubble"} and len(exhibit["resolved_series"])!=(3 if kind=="bubble" else 2):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Association exhibit requires x/y and optional size coordinates")
            if kind=="bubble" and any(number<=0 for number in exhibit["resolved_series"][2]["values"]):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Bubble sizes must be positive bound values")
            if kind in {"waterfall","bridge"}:
                values=[Decimal(str(self.verifier.value(self.graph,key))) for key in exhibit["series"][0]["evidence_ids"]]
                if len(values)<3 or values[0]+sum(values[1:-1])!=values[-1]:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Bridge endpoint does not reconcile with bound starting value and movements")
        if set(used)!=set(binding["evidence_ids"]):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Binding includes unused evidence; provenance must describe the actual exhibit")
        # Units include scale/currency/dimensions, not only the human label.
        numeric_ids=[key for series in exhibit.get("series",[]) for key in series["evidence_ids"]]
        unit_groups=[[self.graph.resolve(key)["unit"] for key in series["evidence_ids"]] for series in exhibit.get("series",[])] if kind in {"scatter","bubble"} else [[self.graph.resolve(key)["unit"] for key in numeric_ids]]
        for units in unit_groups:
            if units and any(unit!=units[0] for unit in units[1:]):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Chart combines incompatible scales/currencies/dimensions")
        return exhibit
