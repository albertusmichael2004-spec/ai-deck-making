"""Package tools/vscode-studio as a .vsix (no Node/npm needed) and install it into VS Code."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from xml.sax.saxutils import escape
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools/vscode-studio"
OUTPUT = ROOT / "runtime/vscode"

CONTENT_TYPES = """<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension=".json" ContentType="application/json"/>
<Default Extension=".js" ContentType="application/javascript"/>
<Default Extension=".css" ContentType="text/css"/>
<Default Extension=".vsixmanifest" ContentType="text/xml"/>
</Types>"""


def manifest(package):
    return f"""<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011" xmlns:d="http://schemas.microsoft.com/developer/vsx-schema-design/2011">
  <Metadata>
    <Identity Language="en-US" Id="{escape(package['name'])}" Version="{escape(package['version'])}" Publisher="{escape(package['publisher'])}"/>
    <DisplayName>{escape(package['displayName'])}</DisplayName>
    <Description xml:space="preserve">{escape(package['description'])}</Description>
    <Categories>{escape(','.join(package['categories']))}</Categories>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value="{escape(package['engines']['vscode'])}"/>
      <Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="workspace"/>
    </Properties>
  </Metadata>
  <Installation><InstallationTarget Id="Microsoft.VisualStudio.Code"/></Installation>
  <Dependencies/>
  <Assets><Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/></Assets>
</PackageManifest>"""


def build():
    package = json.loads((SOURCE / "package.json").read_text(encoding="utf-8"))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    target = OUTPUT / f"{package['name']}-{package['version']}.vsix"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("extension.vsixmanifest", manifest(package))
        for path in sorted(SOURCE.rglob("*")):
            if path.is_file():
                archive.write(path, "extension/" + path.relative_to(SOURCE).as_posix())
    return target


def code_command():
    located = shutil.which("code")
    if located:
        return located
    candidate = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Microsoft VS Code/bin/code.cmd"
    return str(candidate) if candidate.is_file() else None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-only", action="store_true", help="Create the .vsix without installing it")
    options = parser.parse_args(argv)
    vsix = build()
    print(f"Built {vsix}")
    if options.build_only:
        return 0
    code = code_command()
    if code is None:
        print("VS Code's `code` command was not found. Install the .vsix via Extensions > ... > Install from VSIX.", file=sys.stderr)
        return 1
    result = subprocess.run([code, "--install-extension", str(vsix), "--force"], check=False)
    if result.returncode == 0:
        print("Installed. Run 'Developer: Reload Window', then use the 'Studio' and 'Deck Preview' buttons in the status bar.")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
