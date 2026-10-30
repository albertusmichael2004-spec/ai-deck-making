import ast
import json
from decimal import Decimal, InvalidOperation, localcontext, Context, DecimalException

from state.errors import StudioError, ErrorCode

CALCULATION_PRECISION=28


def number(value):
    if isinstance(value, bool):
        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Boolean is not numeric evidence")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Input is not an explicit numeric value") from exc
    if not result.is_finite():
        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Numeric input must be finite")
    return result


def calculate(formula: str, inputs: dict, input_units=None, result_unit=None):
    """Small arithmetic contract with Decimal; no eval, calls, attributes or shell."""
    if len(formula) > 4096:
        raise StudioError(ErrorCode.SECURITY_BLOCK, "Calculation formula exceeds limit")
    try:
        tree = ast.parse(formula, mode="eval")
    except SyntaxError as exc:
        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Invalid arithmetic formula") from exc
    if sum(1 for _ in ast.walk(tree)) > 256:
        raise StudioError(ErrorCode.SECURITY_BLOCK, "Calculation exceeds complexity budget")
    used = set()
    def dimension(unit):
        if "dimensions" in unit:return {key:value for key,value in unit["dimensions"].items() if value}
        label=unit["label"]
        if label in {"ratio","fraction","percentage","percent"}:return {}
        if label=="currency":
            if not unit.get("currency"):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Currency units require an ISO currency code")
            return {"currency:"+unit["currency"]:1}
        return {label:1}
    def combine(first,second,sign):
        result=dict(first)
        for key,value in second.items():result[key]=result.get(key,0)+sign*value
        return {key:value for key,value in result.items() if value}
    def visit(node):
        if isinstance(node, ast.Expression): return visit(node.body)
        if isinstance(node, ast.Name):
            if node.id not in inputs: raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Unknown calculation input", variable=node.id)
            used.add(node.id)
            unit=(input_units or {}).get(node.id)
            return (number(inputs[node.id])*number(unit.get("scale",1)) if unit else number(inputs[node.id]),dimension(unit) if unit else {})
        if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
            return number(ast.get_source_segment(formula, node)),{}
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value,dims=visit(node.operand)
            return value * (-1 if isinstance(node.op, ast.USub) else 1),dims
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            (left,left_dim),(right,right_dim)=visit(node.left),visit(node.right)
            if isinstance(node.op,(ast.Add,ast.Sub)) and left_dim!=right_dim:
                raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Addition/subtraction requires dimensionally compatible units")
            if isinstance(node.op, ast.Add): return left + right,left_dim
            if isinstance(node.op, ast.Sub): return left - right,left_dim
            if isinstance(node.op, ast.Mult): return left * right,combine(left_dim,right_dim,1)
            if right == 0: raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Division by zero")
            return left / right,combine(left_dim,right_dim,-1)
        raise StudioError(ErrorCode.SECURITY_BLOCK, "Unsupported arithmetic syntax")
    try:
        with localcontext(Context(prec=CALCULATION_PRECISION)):
            value,dims = visit(tree)
            if used != set(inputs):
                raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Declared calculation inputs must all be used")
            if result_unit is not None:
                if dims!=dimension(result_unit):raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Formula dimensions do not match declared result units")
                scale=number(result_unit.get("scale",1))
                if scale<=0:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Unit scale must be positive")
                value=value/scale
    except DecimalException as exc:
        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Arithmetic exceeds the supported decimal range") from exc
    return str(value)


def verify_number(displayed, actual, tolerance="0"):
    tolerance = number(tolerance)
    if tolerance < 0: raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Negative tolerance")
    return abs(number(displayed) - number(actual)) <= tolerance


def validate_units(nodes: dict, result_unit: dict):
    if not isinstance(result_unit, dict) or not result_unit.get("label"):
        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Calculation requires explicit result units")
    if any(node.get("unit",{}).get("label") in {None,"unspecified"} for node in nodes.values()):
        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Input units must be specified before calculation")
    for unit in [result_unit,*[node["unit"] for node in nodes.values()]]:
        if number(unit.get("scale",1))<=0:raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Unit scale must be positive")
