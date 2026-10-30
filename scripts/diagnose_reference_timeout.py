from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree
root=Path(__file__).resolve().parents[1]
source=root/'library/references/database/originals/Kick Off - FMCG Manufacturing Pre-FS.pptx'
with ZipFile(source) as package:
    names=[name for name in package.namelist() if name.startswith('ppt/slides/slide') and name.endswith('.xml') and '/_rels/' not in name]
    print('bytes',source.stat().st_size,'slides',len(names))
    for name in sorted(names,key=lambda n:int(n.rsplit('slide',1)[1].split('.')[0]))[:3]:
        slide=ElementTree.fromstring(package.read(name))
        print(name,'shapes',sum(1 for node in slide.iter() if node.tag.endswith('}sp')),'runs',sum(1 for node in slide.iter() if node.tag.endswith('}r')),'charts',package.read(name).count(b':chart'))
