"""Checkpoint verified application fixes; retain native/UI limits explicitly."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET
import zipfile
from state.io import read_yaml, write_yaml, write_json
from ir.validation import validate

root=Path(__file__).resolve().parents[1]
def totals(name):
    suite=ET.parse(root/name).getroot().find("testsuite")
    return {key:int(suite.get(key,0)) for key in ["tests","failures","errors","skipped"]}

verified=totals("implementation/style_verified.xml")
assert verified["tests"] and not any(verified[key] for key in ["failures","errors","skipped"]),verified
preflight=totals("implementation/style_preflight.xml")
assert preflight["tests"] and not any(preflight[key] for key in ["failures","errors","skipped"]),preflight
verified={key:verified[key]+preflight[key] for key in verified}
names=[".vscode/settings.json","schemas/patch_spec/1.2.json","schemas/patch_plan/1.1.json",
       "src/cli/codex_launcher.py","src/cli/main.py","src/state/workspace.py",
       "src/presentation/backends/styles.py","src/presentation/backends/mutations.py","src/presentation/backends/ooxml.py","src/presentation/backends/windows_probe.py",
       "src/presentation/rendering/diagnostics.py","src/presentation/rendering/native.py",
       "src/presentation/live/session.py","src/presentation/live/windows.py","src/presentation/live/batch.py","src/orchestration/repair.py",
       "scripts/powerpoint_render_worker.py","scripts/maintenance_style_contract.py","scripts/test_style_regression.py","scripts/checkpoint_style_fixes.py",
       "tests/integration/test_style_patches.py","tests/unit/test_approval_notifications.py","tests/unit/test_native_render_diagnostics.py","tests/unit/test_office_preflight.py","docs/STYLE_REVISION.md"]
for name in names:
    if name.endswith(".py"):ast.parse((root/name).read_text(encoding="utf-8-sig"),filename=name)
checkpoint="implementation/CHECKPOINTS/style_fixes_20261022.zip"
report_path="implementation/PHASE_REPORTS/style_fixes_20261022.json"
report={"status":"scoped_file_logic_verified_native_qa_and_ui_check_pending","time":datetime.now(timezone.utc).isoformat(),
        "tests":{"verified":verified,"reports":["implementation/style_verified.xml","implementation/style_preflight.xml"],"broad_attempt":totals("implementation/style_logic_final.xml"),"broad_report":"implementation/style_logic_final.xml","broad_completed":False,"broad_stop_reason":"Windows process creation error 8 and Python MemoryError under system memory pressure; not a passing regression run"},
        "changes":["Versioned file patch operations for gradients, connector conversion and filled chart series/point colors","Original chart caches, workbooks, untouched ZIP payloads, protected scopes and stale-fingerprint checks preserved","Live preflight directs unsupported styling to file revision before mutation","Actionable native/Office errors and cleanup failures retain original cause; borrowed user documents remain untouched","Codex approval/completion terminal notifications and VS Code visual/audio bell enabled, approval remains on-request","CLI reports exhausted memory as user action rather than filesystem failure"],
        "native_probe_observed":{"time":"2026-10-22T09:16:31Z","available":True,"version":"16.0","open_presentations":1,"errors":[],"read_only":True},
        "resource_observation":{"total_ram_mb":16055,"available_ram_mb":359,"available_virtual_mb":32,"total_virtual_mb":52852,"later_available_virtual_mb":3565,"scope":"Windows system snapshot, not Studio process allocation","interpretation":"System RAM/commit pressure can stall Python, extensions and Office; user applications were not closed"},
        "notification_config_parse":{"accepted_by_installed_cli":True,"interactive_ui_verified":False},
        "limitations":["No actual user presentation was edited","Real native render/visual QA still requires an appropriate Office session; one saved user deck remained open","Live rollback cannot safely apply the new styles; file revision is supported","Line/marker chart palettes require a separate operation","Full regression did not complete because of system memory exhaustion","Restart Codex CLI and reload VS Code to apply terminal alert settings; no Windows toast guarantee"],
        "documentation":"docs/STYLE_REVISION.md","sources":["https://learn.chatgpt.com/docs/config-file/config-advanced#notifications","https://github.com/microsoft/vscode/blob/main/src/vs/workbench/contrib/terminal/common/terminalConfiguration.ts"]}
write_json(root/report_path,report)
markdown="implementation/PHASE_REPORTS/style_fixes_20261022.md"
(root/markdown).write_text(f'''# Perbaikan styling, Office, dan notifikasi

{verified['tests']} tes terarah lolos. Dukungan baru: gradasi linear, konversi connector ke rectangle dengan identitas tetap, serta fill seri/titik chart native. Angka 3/27, tahun 2026/2029, workbook tertanam dan bagian ZIP lain dipertahankan dalam pengujian. Scope terlindungi, fingerprint kedaluwarsa dan kontrak lama tetap menolak operasi yang tidak sah.

Live preflight mengarahkan styling baru ke revisi file sebelum perubahan dimulai. QA, Critic, evidence, canonical commit dan recovery gate tetap berlaku. Native worker menjelaskan Office busy, automation denied dan presentasi terbuka; error cleanup tidak menutupi error awal dan dokumen pengguna tidak ditutup.

Notifikasi izin/completion Codex memakai terminal bell dengan kondisi always; VS Code mengaktifkan bell visual/suara. Parser CLI menerima konfigurasinya. Reload VS Code dan mulai sesi CLI baru; pemeriksaan UI interaktif belum dilakukan dan Windows toast tidak dijamin.

Probe PowerPoint terbaru berhasil, tetapi satu presentasi tersimpan masih terbuka. Render native atas revisi belum diverifikasi. Tidak ada PPT pengguna yang diedit pada pekerjaan perbaikan aplikasi ini.

Regresi luas tidak selesai: Windows error 8 dan MemoryError. Snapshot sistem menunjukkan RAM tersedia 359 MB dari 16055 MB dan sisa virtual/commit 32 MB; pengamatan berikutnya mencatat virtual tersedia 3565 MB. Ini pengukuran sistem, bukan penggunaan memori Studio. Laporan gagal tetap disimpan; tidak diklaim sebagai hasil lolos. Simpan pekerjaan dan tutup aplikasi yang tidak diperlukan sebelum uji native/regresi penuh.

Lihat docs/STYLE_REVISION.md dan laporan JSON untuk kontrak, bukti, dan batasannya.
''',encoding="utf-8")
state_path=root/"implementation/IMPLEMENTATION_STATUS.yaml"
state=read_yaml(state_path)
state.setdefault("maintenance",{})["style_fixes"]={"status":report["status"],"feature_report":report_path,"tests":verified,"last_checkpoint":{"type":"verified_maintenance_snapshot","path":checkpoint}}
validate(root,"implementation_state",state)
write_yaml(state_path,state)
names.extend(["implementation/IMPLEMENTATION_STATUS.yaml",report_path,markdown,"implementation/style_verified.xml","implementation/style_preflight.xml","implementation/style_logic_final.xml","implementation/style_alert_cleanup.xml"])
payloads={name:(root/name).read_bytes() for name in names}
manifest={name:hashlib.sha256(data).hexdigest() for name,data in payloads.items()}
with zipfile.ZipFile(root/checkpoint,"x",zipfile.ZIP_DEFLATED) as archive:
    for name,data in payloads.items():archive.writestr(name,data)
    archive.writestr("CHECKPOINT_MANIFEST.json",json.dumps(manifest,indent=2))
with zipfile.ZipFile(root/checkpoint) as archive:
    assert all(hashlib.sha256(archive.read(name)).hexdigest()==digest for name,digest in manifest.items())
print(json.dumps({"tests":verified,"checkpoint":checkpoint,"report":markdown},indent=2))
