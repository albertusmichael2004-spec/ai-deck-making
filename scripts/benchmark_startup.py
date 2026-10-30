"""Measure actual launcher/menu startup in fresh Python processes (no Office calls)."""
import argparse
import builtins
import ctypes
from ctypes import wintypes
import io
import json
import os
from pathlib import Path
import runpy
import statistics
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


def memory():
    if os.name!='nt':return None
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in ['PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage']]
    counters=Counters();counters.cb=ctypes.sizeof(counters)
    ctypes.windll.kernel32.GetCurrentProcess.restype=wintypes.HANDLE
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    if not ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(),ctypes.byref(counters),counters.cb):return None
    return round(counters.PeakWorkingSetSize/1048576,2)


def worker(entry):
    sys.path[:0]=[str(ROOT),str(ROOT/'src'),str(ROOT/'runtime/python_packages')]
    original_stdout=sys.stdout
    output=io.StringIO();sys.stdout=output
    original_input=builtins.input
    reached=[]
    started=time.perf_counter();cpu=time.process_time()
    def answer(prompt=''):
        reached.append(time.perf_counter()-started)
        return 'q'
    builtins.input=answer
    try:
        sys.argv=['run.py','--in-terminal'] if entry=='launcher' else ['studio']
        try:
            if entry=='launcher':runpy.run_path(str(ROOT/'run.py'),run_name='__main__')
            else:runpy.run_module('cli.main',run_name='__main__')
        except SystemExit as exc:
            if exc.code not in [None,0]:raise
    finally:
        sys.stdout=original_stdout;builtins.input=original_input
    assert reached and 'pilih aktivitas' in output.getvalue(),output.getvalue()
    return {'entry':entry,'seconds_to_menu':round(reached[0],4),'process_cpu_seconds':round(time.process_time()-cpu,4),'peak_working_set_mb':memory(),'loaded_modules':len(sys.modules),'heavy_imports':[name for name in ['pptx','openpyxl','fitz','docx','PIL.Image','win32com.client','jsonschema'] if name in sys.modules]}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--worker',choices=['launcher','cli'])
    parser.add_argument('--label',default='before')
    parser.add_argument('--repeats',type=int,default=3)
    args=parser.parse_args()
    if args.worker:
        print(json.dumps(worker(args.worker)))
    else:
        samples=[]
        for entry in ['launcher','cli']:
            for _ in range(args.repeats):
                result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker',entry],cwd=ROOT,capture_output=True,text=True,timeout=90)
                if result.returncode:raise RuntimeError(result.stdout+result.stderr)
                sample=json.loads(result.stdout.strip().splitlines()[-1]);samples.append(sample)
                print(json.dumps(sample),flush=True)
        report={'label':args.label,'python':sys.executable,'note':'CPU and memory measure the menu process; launcher probe subprocess CPU is excluded. Fresh processes with warm filesystem cache, not a cold boot.','samples':samples,'median':{entry:{key:statistics.median(row[key] for row in samples if row['entry']==entry and row[key] is not None) for key in ['seconds_to_menu','process_cpu_seconds','peak_working_set_mb']} for entry in ['launcher','cli']}}
        destination=ROOT/'implementation/PHASE_REPORTS'/f'startup_performance_{args.label}.json'
        destination.write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report['median'],indent=2))
