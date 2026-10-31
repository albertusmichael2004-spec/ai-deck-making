"""Terminal project picker plus native file selection; uses existing Studio APIs."""
from cli.codex_launcher import launch
from state.errors import StudioError, ErrorCode
from state.intake import ProjectIntake
from state.workspace import Workspaces


def pick_files(folder=False, target=False):
    try:
        import tkinter as tk
        from tkinter import filedialog
        window = tk.Tk()
        window.withdraw()
        try:
            window.attributes("-topmost", True)
            if folder:
                selected = filedialog.askdirectory(parent=window, title="Pilih folder bahan project")
                return [selected] if selected else []
            return list(filedialog.askopenfilenames(parent=window, title="Pilih PPT kerja" if target else "Tambahkan file ke project", filetypes=[("PowerPoint", "*.pptx")] if target else [("Semua file", "*.*")]))
        finally:
            window.destroy()
    except ImportError as exc:
        raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE, "File picker is unavailable; use studio project import --source FILE", reason=str(exc)) from exc
    except (tk.TclError, RuntimeError) as exc:
        raise StudioError(ErrorCode.CAPABILITY_UNAVAILABLE, "File picker is unavailable; use studio project import --source FILE", reason=str(exc)) from exc


class ProjectMenu:
    def __init__(self, root, reader=input, writer=print, picker=pick_files, launcher=launch):
        self.workspaces = Workspaces(root)
        self.read, self.write, self.picker, self.launcher = reader, writer, picker, launcher
        self.initial_prompt = None

    def _choose_material_project(self):
        while True:
            rows = [row for row in self.workspaces.list() if row["category"] == "project"]
            self.write("\nPilih tujuan bahan PDF/data/dokumen")
            for index, row in enumerate(rows, 1):
                marker = " *" if row["project_id"] == self.workspaces.active() else ""
                self.write(f"  [{index}] {row['name']}{marker}")
            self.write("  [N] Buat project   [O] Others / edit cepat   [B] Kembali")
            choice = self.read("Pilih tujuan: ").strip().lower()
            if choice == "b":
                return None
            if choice == "n":
                name = self.read("Nama project/bisnis: ").strip()
                if not name:
                    self.write("Nama project tidak boleh kosong.")
                    continue
                return self.workspaces.create(name)
            if choice == "o":
                return self.choose_others()
            if choice.isdigit() and 1 <= int(choice) <= len(rows):
                return self.workspaces.select(rows[int(choice) - 1]["project_id"])
            self.write("Pilihan tidak dikenal.")

    def import_project_materials(self):
        project = self._choose_material_project()
        if project is None:
            return
        self.write("[1] Pilih satu atau beberapa file   [2] Pilih folder bahan   [B] Kembali")
        choice = self.read("Jenis impor: ").strip().lower()
        if choice == "b":
            return
        if choice not in {"1", "2"}:
            self.write("Pilihan tidak dikenal.")
            return
        selected = self.picker(folder=choice == "2")
        if not selected:
            self.write("Tidak ada file yang dipilih.")
            return
        imported = ProjectIntake(self.workspaces, project).import_paths(selected, "source")
        self.write(f"Tersimpan: {len(imported)} bahan sebagai source project. File asli tetap utuh.")

    def start_menu(self):
        """Choose the existing Codex workflow or one of the explicit ingestion paths."""
        while True:
            self.write("\nAI Presentation Studio — pilih aktivitas")
            self.write("[1] Mulai / lanjutkan Codex CLI atau Claude Code")
            self.write("[2] Ingest ulang Knowledge Base (panduan PDF, Markdown, JSON, CSV, dan lainnya)")
            self.write("[3] Impor PDF/data/dokumen sebagai bahan project")
            self.write("[4] Kelola Database / references PPT")
            self.write("[Q] Keluar")
            try:
                choice = self.read("Pilih aktivitas: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                self.write("\nStudio ditutup. Data project tetap tersimpan.")
                return 0
            if choice == "q":
                return 0
            try:
                if choice == "1":
                    self.run()
                elif choice == "2":
                    from knowledge.store import KnowledgeStore
                    result = KnowledgeStore(self.workspaces.root).ingest("consulting_deck_knowledge_v1")
                    status = "sudah terbaru" if result.get("status") == "unchanged" else "selesai"
                    self.write(f"Knowledge ingestion {status}: {result.get('files', 0)} file, {result.get('chunks', 0)} chunks.")
                elif choice == "3":
                    self.import_project_materials()
                elif choice == "4":
                    self.database()
                else:
                    self.write("Pilihan tidak dikenal.")
            except (StudioError, OSError) as exc:
                self.write(f"Belum dapat diselesaikan: {exc}")
            except (EOFError, KeyboardInterrupt):
                self.write("\nStudio ditutup. Data project tetap tersimpan.")
                return 0

    def database(self, project_id=None):
        from references.catalog import ReferenceCatalog
        from presentation.rendering.native import NativeRenderer
        catalog = ReferenceCatalog(self.workspaces.root, project_id=project_id, renderer=NativeRenderer(self.workspaces.root))
        scope = "project" if project_id else "database"
        while True:
            self.write("\n" + ("References project" if project_id else "Database — references umum"))
            self.write("[1] Tambah file   [2] Tambah folder   [3] Lihat file\n[4] Indeks PPT / preview native   [B] Kembali")
            choice = self.read("Pilih: ").strip().lower()
            if choice == "b":
                return
            try:
                if choice in {"1", "2"}:
                    selected = self.picker(folder=choice == "2")
                    if selected:
                        rows = catalog.import_paths(selected, scope=scope)
                        self.write(f"Tersimpan: {len(rows)} references. File asli dipertahankan.")
                elif choice == "3":
                    for row in catalog.files():
                        if row["scope"] == scope:
                            self.write(f"  {row['relative_path']} | {'utuh' if row['verified'] else 'BERUBAH/HILANG'}")
                elif choice == "4":
                    report = catalog.store(scope).ingest()
                    self.write(str(report["counts"]))
                    for row in report["items"]:
                        if row["status"] == "failed":
                            self.write(f"Belum terindeks: {row['source_path']} | {row['error']}")
                else:
                    self.write("Pilihan tidak dikenal.")
            except (StudioError, OSError) as exc:
                self.write(f"Belum dapat diselesaikan: {exc}")

    def choose_others(self):
        while True:
            rows = [row for row in self.workspaces.list() if row["category"] == "others"]
            if not rows:
                return self.workspaces.create_others()
            self.write("\nOthers — edit cepat tersimpan")
            for index, row in enumerate(rows, 1):
                title = row["target_name"] or "PPT baru"
                self.write(f"  [{index}] {title} | {row['last_opened_at']}")
            choice = self.read("[N/Enter] Edit baru  [B] Kembali  atau nomor: ").strip().lower()
            if choice in {"", "n"}:
                return self.workspaces.create_others()
            if choice == "b":
                return None
            if choice.isdigit() and 1 <= int(choice) <= len(rows):
                return self.workspaces.select(rows[int(choice) - 1]["project_id"])
            self.write("Pilihan tidak dikenal.")

    def choose(self):
        while True:
            rows = [row for row in self.workspaces.list() if row["category"] != "others"]
            active = self.workspaces.active()
            self.write("\nAI Presentation Studio — pilih project")
            for index, row in enumerate(rows, 1):
                marker = " *" if row["project_id"] == active else ""
                status = "PPT tersedia" if row["deck_exists"] else "PPT belum dibuat"
                self.write(f"  [{index}] {row['name']}{marker} | {row['file_count']} file | {status}")
            if not rows:
                self.write("  Belum ada project pengguna.")
            self.write("  [N] Buat project/bisnis   [D] Database   [O] Others / edit cepat   [Q] Keluar")
            self.write("  Enter atau ketik permintaan langsung: prompt tanpa project ke Others.")
            raw = self.read("Pilih project / prompt: ").strip()
            selected = raw.lower()
            if selected == "q":
                return None
            if selected == "d":
                self.database()
                continue
            if selected == "n":
                name = self.read("Nama project: ")
                return self.workspaces.create(name)
            if selected == "o":
                project = self.choose_others()
                if project is not None:
                    return project
                continue
            if not selected:
                return self.workspaces.create_others()
            if selected.isdigit() and 1 <= int(selected) <= len(rows):
                return self.workspaces.select(rows[int(selected) - 1]["project_id"])
            if len(raw) > 1 and not selected.isdigit():
                self.initial_prompt = raw
                return self.workspaces.create_others()
            self.write("Pilihan tidak dikenal.")

    def page(self, project):
        while True:
            metadata = self.workspaces.metadata(project)
            self.write(f"\nProject: {metadata['display_name']} | {len(metadata['imports'])} file")
            self.write("PPT kerja: " + ("tersedia" if project.canonical.is_file() else "akan dibuat pada build pertama"))
            self.write("[1] Mulai chat Codex   [2] Lanjut chat terakhir\n[C] Mulai chat Claude Code   [L] Lanjut chat Claude terakhir\n[3] Tambah data/dokumen   [4] Tambah folder bahan\n[5] Tambah gambar/logo    [6] Impor PPT untuk dikerjakan\n[7] Lihat file   [B] Pilih/buat project lain   [Q] Keluar")
            self.write("[D] Database umum" + ("   [R] References project/bisnis ini" if metadata.get("category", "project") == "project" else ""))
            if metadata.get("category") == "others":
                self.write("Hasil: output/Others  |  [8] Ekspor PPT tervalidasi")
            choice = self.read("Pilih: ").strip().lower()
            if choice in {"b", "q"}:
                return choice
            try:
                if choice in {"1", "2"}:
                    code = self.launcher(self.workspaces, project, resume=choice == "2")
                    self.write("Kembali ke project. Data tersimpan." if code == 0 else "Codex berhenti dengan error; project tetap tersimpan. Pilih chat baru jika belum ada sesi untuk dilanjutkan.")
                elif choice in {"c", "l"}:
                    code = self.launcher(self.workspaces, project, resume=choice == "l", agent="claude")
                    self.write("Kembali ke project. Data tersimpan." if code == 0 else "Claude Code berhenti dengan error; project tetap tersimpan. Jika belum login, jalankan Claude Code sekali lalu ketik /login.")
                elif choice == "d":
                    self.database()
                elif choice == "r" and metadata.get("category", "project") == "project":
                    self.database(project.path.name)
                elif choice in {"3", "4", "5", "6"}:
                    role = "asset" if choice == "5" else "target" if choice == "6" else "source"
                    intake = ProjectIntake(self.workspaces, project)
                    selected = self.picker(folder=choice == "4", target=choice == "6")
                    if role == "target" and len(selected) > 1:
                        raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Pilih satu PPTX sebagai file pengerjaan")
                    if selected:
                        items = intake.import_paths(selected, role)
                        if role == "target":
                            intake.initialize_target(items[0])
                            from state.outputs import export_others
                            export_others(self.workspaces.root, project.path.name)
                        self.write(f"Tersimpan: {len(items)} file. File asli dipertahankan.")
                elif choice == "7":
                    for row in ProjectIntake(self.workspaces, project).files():
                        self.write(f"  {row['role']} | {row['relative_path']} | {'utuh' if row['verified'] else 'BERUBAH/HILANG'}")
                    from state.io import logical_path
                    self.write(f"PPT kerja: {logical_path(project.canonical)}")
                    if metadata.get("export"):
                        self.write("Hasil Others: " + metadata["export"]["path"])
                elif choice == "8" and metadata.get("category") == "others":
                    from state.outputs import export_others
                    self.write("Tersimpan: " + export_others(self.workspaces.root, project.path.name, required=True)["path"])
                else:
                    self.write("Pilihan tidak dikenal.")
            except (StudioError, OSError) as exc:
                self.write(f"Belum dapat diselesaikan: {exc}")

    def run(self, project_id=None, *, others=False):
        try:
            project = self.workspaces.create_others() if others else self.workspaces.select(project_id) if project_id else None
            while True:
                if project is None:
                    try:
                        project = self.choose()
                    except StudioError as exc:
                        self.write(str(exc))
                        continue
                if project is None:
                    return 0
                if self.initial_prompt:
                    prompt, self.initial_prompt = self.initial_prompt, None
                    try:
                        self.launcher(self.workspaces, project, resume=False, prompt=prompt)
                    except (StudioError, OSError) as exc:
                        self.write(str(exc))
                if self.page(project) == "q":
                    return 0
                project = None
        except (EOFError, KeyboardInterrupt):
            self.write("\nProject tetap tersimpan. Jalankan Studio lagi untuk melanjutkan.")
            return 0
