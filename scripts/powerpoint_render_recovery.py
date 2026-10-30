"""Recover one proven render copy without quitting PowerPoint or user documents."""
import argparse
import json
from pathlib import Path
import sys

root=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(root/'src'),str(root/'runtime/python_packages')]
from state.io import write_json
from presentation.rendering.recovery import recover_render_copy
from security.paths import PathPolicy
import pythoncom

parser=argparse.ArgumentParser()
parser.add_argument('--source',type=Path,required=True)
parser.add_argument('--sha256',required=True)
args=parser.parse_args()
args.source=PathPolicy([root/'runtime/native_render'],[root/'runtime/native_render']).check(args.source)
pythoncom.CoInitialize()
try:
    try:result=recover_render_copy(root,args.source,args.sha256)
    except Exception as exc:result={'status':'unavailable','reason':str(exc)}
    write_json(args.source.parent/'recovery.json',result)
    print(json.dumps(result,indent=2))
finally:
    pythoncom.CoUninitialize()
