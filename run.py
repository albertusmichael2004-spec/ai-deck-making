"""Start the Studio activity menu using a Python runtime with project dependencies."""
import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REQUIRED_IMPORTS = (
    "yaml",
    "jsonschema",
    "pptx",
    "lxml",
    "openpyxl",
    "fitz",
    "docx",
    "PIL",
    "win32com",
)


def _candidate_interpreters():
    """Prefer a project venv, then the caller and Python installations on PATH."""
    venv_python = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    seen = set()
    for candidate in [venv_python,Path(sys.executable)]:
        key = os.path.normcase(os.path.abspath(candidate))
        if key not in seen:
            seen.add(key)
            yield candidate
    # PATH can contain slow/network locations. Search it only after local
    # candidates have actually failed rather than on every healthy venv launch.
    for command in ("python", "python3"):
        located = shutil.which(command)
        if located:
            candidate=Path(located)
            key=os.path.normcase(os.path.abspath(candidate))
            if key not in seen:
                seen.add(key)
                yield candidate


def _has_project_dependencies(interpreter):
    """Check Python version and imports without changing any environment."""
    runtime_packages = str(ROOT / "runtime" / "python_packages")
    if os.path.normcase(os.path.abspath(interpreter)) == os.path.normcase(os.path.abspath(sys.executable)):
        if sys.version_info < (3,12):return False
        previous_path=sys.path[:]
        try:
            sys.path.insert(0,runtime_packages)
            return all(importlib.util.find_spec(name) is not None for name in REQUIRED_IMPORTS)
        except (ImportError,ValueError):
            return False
        finally:
            sys.path[:]=previous_path
    code = (
        "import importlib.util,sys; "
        "sys.path.insert(0,sys.argv[1]); "
        f"missing=[name for name in {REQUIRED_IMPORTS!r} if importlib.util.find_spec(name) is None]; "
        "print(','.join(missing)); "
        "raise SystemExit(1 if sys.version_info < (3,12) or missing else 0)"
    )
    try:
        result = subprocess.run(
            [str(interpreter), "-c", code, runtime_packages],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _find_project_interpreter():
    for candidate in _candidate_interpreters():
        if candidate.is_file() and _has_project_dependencies(candidate):
            return candidate
    return None


def _studio_arguments(options):
    arguments = ["--root", str(ROOT)]
    if options.others:
        arguments.extend(["project", "others"])
    return arguments


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in-terminal", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--others", action="store_true", help="Start a quick edit without a named project")
    options = parser.parse_args(argv)
    interpreter = _find_project_interpreter()
    if interpreter is None:
        print(
            "Python ini belum memiliki dependency AI Presentation Studio. "
            "Siapkan environment project dengan perintah berikut:",
            file=sys.stderr,
        )
        print(f'  & "{sys.executable}" -m venv .venv', file=sys.stderr)
        print("  .\\.venv\\Scripts\\python.exe -m pip install -e '.[native,test]'", file=sys.stderr)
        print("Lalu jalankan kembali run.py.", file=sys.stderr)
        return 1

    using_fallback = os.path.normcase(os.path.abspath(interpreter)) != os.path.normcase(os.path.abspath(sys.executable))
    if using_fallback:
        print(f"Memakai environment project: {interpreter}")

    # Editors using an output panel / pythonw cannot host an interactive TUI.
    # Open one real console; the child flag prevents opening another window.
    interactive = all(stream is not None and stream.isatty() for stream in (sys.stdin, sys.stdout))
    if os.name == "nt" and not interactive and not options.in_terminal:
        environment = dict(os.environ, PYTHONUTF8="1")
        subprocess.Popen(
            [str(interpreter), str(ROOT / "run.py"), "--in-terminal"] + (["--others"] if options.others else []),
            cwd=ROOT,
            env=environment,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        return 0

    os.chdir(ROOT)
    if using_fallback:
        # Enter the CLI directly: avoid another launcher dependency probe.
        environment = dict(os.environ, PYTHONUTF8="1")
        environment["PYTHONPATH"] = os.pathsep.join(
            [str(ROOT / "src"), str(ROOT / "runtime/python_packages"), environment.get("PYTHONPATH", "")]
        )
        return subprocess.run(
            [str(interpreter), "-m", "cli.main"] + _studio_arguments(options),
            cwd=ROOT,
            env=environment,
            check=False,
        ).returncode

    sys.path[:0] = [str(ROOT / "src"), str(ROOT / "runtime/python_packages")]
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    from cli.main import main as studio_main
    return studio_main(_studio_arguments(options))


if __name__ == "__main__":
    raise SystemExit(main())
