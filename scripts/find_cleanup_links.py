"""Read-only junction inventory; never traverse link targets or delete files."""
import argparse
import json
import os
from pathlib import Path

parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);parser.add_argument('--report',required=True)
args=parser.parse_args();root=Path(args.root).resolve()
native='\\\\?\\'+str(root) if os.name=='nt' else str(root)
pending=[native];links=[];count=0
def logical(path):return path[4:] if path.startswith('\\\\?\\') else path
while pending:
    directory=pending.pop();count+=1
    with os.scandir(directory) as entries:
        for entry in entries:
            if entry.is_symlink():
                info=entry.stat(follow_symlinks=False)
                links.append({'path':logical(entry.path),'directory':bool(getattr(info,'st_file_attributes',0)&16)})
            elif entry.is_dir(follow_symlinks=False):
                info=entry.stat(follow_symlinks=False)
                if getattr(info,'st_reparse_tag',0) in {0xA0000003,0xA000000C}:links.append({'path':logical(entry.path),'directory':True})
                else:pending.append(entry.path)
    if count%2000==0:print('Scanned directories:',count,flush=True)
Path(args.report).write_text(json.dumps({'root':str(root),'directories':count,'links':links},indent=2),encoding='utf-8')
print('Link inventory complete:',count,'directories,',len(links),'links',flush=True)
