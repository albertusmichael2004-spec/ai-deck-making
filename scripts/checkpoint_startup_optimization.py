"""Publish measured startup/resource results and a recoverable maintenance snapshot."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree
import zipfile

ROOT=Path(__file__).resolve().parents[1]
from state.io import read_json,read_yaml,write_json,write_yaml


def totals(filename):
    suite=ElementTree.parse(ROOT/filename).getroot().find('testsuite')
    return {key:int(suite.get(key,0)) for key in ['tests','failures','errors','skipped']}


before=read_json(ROOT/'implementation/PHASE_REPORTS/startup_performance_before_warm.json')
after=read_json(ROOT/'implementation/PHASE_REPORTS/startup_performance_after_final.json')
checks={name:totals(name) for name in ['implementation/startup_logic_final.xml','implementation/startup_all_unit.xml','implementation/startup_reference_memory.xml','implementation/startup_junction_checks.xml','implementation/startup_focused.xml']}
assert all(value['tests'] and not value['errors'] and not value['failures'] and not value['skipped'] for value in checks.values()),checks
files=[path for folder in ['src','scripts'] for path in (ROOT/folder).rglob('*.py')]+[ROOT/'run.py',ROOT/'main.py']
for path in files:ast.parse(path.read_text(encoding='utf-8-sig'),filename=str(path))
improvements={entry:{key:round(100*(1-after['median'][entry][key]/before['median'][entry][key]),1) for key in ['seconds_to_menu','process_cpu_seconds','peak_working_set_mb']} for entry in ['launcher','cli']}
report={'status':'startup_and_logic_verified_native_retest_pending','time':datetime.now(timezone.utc).isoformat(),'before':before['median'],'after':after['median'],'improvement_percent':improvements,'method':after['note'],'syntax_checked_python_files':len(files),'tests':checks,'test_scope':read_json(ROOT/'implementation/PHASE_REPORTS/startup_test_scope.json'),'observed_causes':['Native locator refresh took 72681 ms in VS Code log 20261022T142735','Healthy venv startup launched a second Python dependency probe and eagerly searched PATH','Parser registration imported optional research/design/review/render engines','Schema and image libraries were loaded before the menu was needed','File import hashed the same complete source twice','Reference ingestion retained the raw PPT media package while a native worker loaded it'],'changes':['Deferred optional engine and schema imports; validation logic retained','In-process dependency check only for the already running interpreter; PATH discovery deferred','Both main.py and run.py use the same environment-aware launcher; CLI handles unrelated cwd','run_studio.cmd launches directly without waiting for editor activation','Disable Python A/B experiments in this workspace; exclude generated folders from Explorer','Single source digest per inspection; imported bytes still reverified after copy','Release raw PPT media before native rendering; retain exact structural graphs'],'limitations':['Measurements are for Python menu startup; exclude VS Code/PowerPoint memory and Python process bootstrap','Baseline and final samples used fresh processes with warm filesystem caches; wall time still depends on machine load and storage','Python process CPU excludes the old dependency-probe child, so old total CPU was higher than recorded','Native render/live tests were not rerun while an editable user PowerPoint presentation was open','Editor activation after Reload Window has not been controlled or measured here'],'official_configuration_reference':'https://github.com/microsoft/vscode-python/wiki/ab-experiments'}
destination=ROOT/'implementation/PHASE_REPORTS/startup_optimization_20261022.json'
write_json(destination,report)
bm=before['median']['launcher'];am=after['median']['launcher']
text=f'''# Evaluasi startup dan resource Studio

Perubahan startup dan regresi logika telah diverifikasi. Render/live PowerPoint perlu diuji pada sesi tanpa presentasi pengguna terbuka.

| Pengukuran proses menu | Sebelum | Sesudah |
|---|---:|---:|
| Median waktu ke menu | {bm['seconds_to_menu']:.2f} detik | {am['seconds_to_menu']:.2f} detik |
| Median waktu CPU proses | {bm['process_cpu_seconds']:.2f} detik | {am['process_cpu_seconds']:.2f} detik |
| Median memori puncak | {bm['peak_working_set_mb']:.2f} MB | {am['peak_working_set_mb']:.2f} MB |

Lima proses baru per jalur, filesystem cache hangat. Angka tidak mencakup waktu aktivasi/memori VS Code, startup interpreter, atau PowerPoint. Waktu CPU probe anak pada versi lama juga tidak tercakup.

Penyebab yang ditemukan: locator editor 72,7 detik; probe Python tambahan; pencarian PATH sebelum diperlukan; import engine, schema, dan gambar saat menu dibuka; hashing file duplikat; paket media PPT masih ditahan saat worker render membuka deck.

Engine sekarang dimuat saat dipilih. Probe untuk interpreter aktif berjalan dalam proses yang sama. Validasi schema tetap dijalankan ketika kontrak digunakan; hash, evidence, Critic, native QA, protected objects dan recovery gate dipertahankan. Tidak ada penurunan kualitas gambar/render atau perubahan PPT asli.

Seluruh {checks['implementation/startup_logic_final.xml']['tests']} tes logika/file terpilih lolos; syntax {len(files)} file Python diperiksa. Laporan JSON mencatat pemilihan tes serta tes native yang tidak dijalankan karena presentasi pengguna sedang terbuka. Tes approval yang sebelumnya tidak stabil sekarang memilih slide pertama yang memang diedit, bukan hasil ranking dengan tie.

Jalankan `run_studio.cmd` untuk membuka Studio langsung. `main.py` dan `run.py` memakai launcher yang sama. Untuk memakai VS Code, lakukan Developer: Reload Window setelah perubahan konfigurasi ini. Jangan menilai waktu aktivasi extension sebagai waktu kerja program.
'''
markdown=destination.with_suffix('.md');markdown.write_text(text,encoding='utf-8')
checkpoint=ROOT/'implementation/CHECKPOINTS/startup_optimization_20261022.zip'
state_path=ROOT/'implementation/IMPLEMENTATION_STATUS.yaml';state=read_yaml(state_path)
state['maintenance']['startup_optimization']={'status':report['status'],'feature_report':destination.relative_to(ROOT).as_posix(),'tests':checks['implementation/startup_logic_final.xml'],'performance':after['median'],'last_checkpoint':{'type':'verified_maintenance_snapshot','path':checkpoint.relative_to(ROOT).as_posix()}}
write_yaml(state_path,state)
names=['run.py','main.py','run_studio.cmd','README.md','.vscode/settings.json','src/cli/main.py','src/cli/data_commands.py','src/cli/research_commands.py','src/cli/knowledge_commands.py','src/cli/reasoning_commands.py','src/cli/design_commands.py','src/cli/reference_commands.py','src/cli/review_commands.py','src/cli/offline_commands.py','src/cli/live_commands.py','src/ir/validation.py','src/security/files.py','src/references/store.py','tests/unit/test_startup_runtime.py','tests/unit/test_run_launcher.py','tests/integration/test_reference_store.py','tests/integration/test_reference_scopes.py','scripts/benchmark_startup.py','scripts/test_startup_regression.py','scripts/checkpoint_startup_optimization.py','implementation/IMPLEMENTATION_STATUS.yaml','implementation/PHASE_REPORTS/startup_performance_before.json','implementation/PHASE_REPORTS/startup_performance_before_warm.json','implementation/PHASE_REPORTS/startup_performance_after.json','implementation/PHASE_REPORTS/startup_performance_after_final.json','implementation/PHASE_REPORTS/startup_optimization_20261022.json','implementation/PHASE_REPORTS/startup_optimization_20261022.md','implementation/PHASE_REPORTS/startup_test_scope.json',*checks.keys()]
payloads={name:(ROOT/name).read_bytes() for name in names}
manifest={name:hashlib.sha256(data).hexdigest() for name,data in payloads.items()}
with zipfile.ZipFile(checkpoint,'x',zipfile.ZIP_DEFLATED) as archive:
    for name,data in payloads.items():archive.writestr(name,data)
    archive.writestr('CHECKPOINT_MANIFEST.json',json.dumps(manifest,indent=2))
with zipfile.ZipFile(checkpoint) as archive:
    assert all(hashlib.sha256(archive.read(name)).hexdigest()==digest for name,digest in manifest.items())
print(json.dumps({'status':report['status'],'tests':checks['implementation/startup_logic_final.xml'],'before':bm,'after':am,'report':str(markdown),'checkpoint':str(checkpoint)},indent=2))
