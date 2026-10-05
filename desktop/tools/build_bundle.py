"""Build, run and package a native standalone application on the current OS."""
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gpx2elev import __version__


def run(args, **kwargs):
    subprocess.run(args, check=True, cwd=ROOT, **kwargs)


def licenses_and_icons():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from gpx2elev.ui import app_icon
    from PIL import Image
    assets = ROOT / "build/assets"
    licenses = assets / "licenses"
    licenses.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(["gpx2elev-build"])
    icon = app_icon().pixmap(128, 128)
    icon.save(str(assets / "icon.png"))
    with Image.open(assets / "icon.png") as image:
        image.save(assets / "icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128)])
        image.resize((1024, 1024)).save(assets / "icon.icns")
    inventory = []
    for distribution in metadata.distributions():
        name = distribution.metadata["Name"]
        if name.lower() in {"pip", "setuptools", "pyinstaller", "pyinstaller-hooks-contrib", "pefile", "altgraph", "pywin32-ctypes"}:
            continue
        target = licenses / name
        target.mkdir(exist_ok=True)
        inventory.append({"package": name, "version": distribution.version,
                          "license": distribution.metadata.get("License-Expression") or distribution.metadata.get("License", "Voir fichiers inclus")})
        for file in distribution.files or []:
            if any(word in str(file).lower() for word in ("license", "copying", "copyright")):
                source = Path(distribution.locate_file(file))
                if source.is_file():
                    destination = target / str(file).replace("/", "_").replace("\\", "_")
                    shutil.copy2(source, destination)
    (licenses / "DEPENDENCIES.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    shutil.copy2(ROOT / "THIRD_PARTY.md", licenses / "THIRD_PARTY.md")
    shutil.copytree(ROOT / "licenses", licenses / "Qt", dirs_exist_ok=True)
    shutil.copy2(ROOT / "gpx2elev/assets/OFL.txt", licenses / "NotoSans-OFL.txt")


def main():
    licenses_and_icons()
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "bundle.spec"])
    release = ROOT / "release"
    release.mkdir(exist_ok=True)
    arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x64"
    if sys.platform == "win32":
        system = "windows"
        binary = ROOT / "dist/gpx2elev/gpx2elev.exe"
    elif sys.platform == "darwin":
        system = "macos"
        binary = ROOT / "dist/gpx2elev.app/Contents/MacOS/gpx2elev"
    else:
        system = "linux"
        binary = ROOT / "dist/gpx2elev/gpx2elev"
    # Exercise the executable, not the source interpreter. Failure prevents packaging/release.
    report = release / f"verification-{system}-{arch}.json"
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    run([str(binary), "--self-test-report", str(report)], env=env, timeout=90)
    if json.loads(report.read_text(encoding="utf-8"))["status"] != "OK":
        raise RuntimeError("Le bundle a échoué à sa vérification.")
    if system == "macos":
        archive = release / f"gpx2elev-{__version__}-{system}-{arch}.zip"
        # ditto preserves .app framework symlinks, unlike Python's zipfile.
        run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", "dist/gpx2elev.app", str(archive)])
    elif system == "windows":
        archive = release / f"gpx2elev-{__version__}-{system}-{arch}.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as output:
            for path in sorted((ROOT / "dist/gpx2elev").rglob("*")):
                if path.is_file():
                    output.write(path, path.relative_to(ROOT / "dist").as_posix())
    else:
        launcher = ROOT / "dist/gpx2elev/gpx2elev.desktop"
        launcher.write_text("[Desktop Entry]\nType=Application\nName=gpx2elev\nExec=gpx2elev %f\nTerminal=false\nCategories=Utility;Science;\nMimeType=application/gpx+xml;\n", encoding="utf-8")
        archive = release / f"gpx2elev-{__version__}-{system}-{arch}.tar.gz"
        with tarfile.open(archive, "w:gz") as output:
            output.add(ROOT / "dist/gpx2elev", arcname="gpx2elev")
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    (release / f"SHA256SUMS-{system}-{arch}.txt").write_text(f"{checksum}  {archive.name}\n", encoding="utf-8", newline="\n")
    print(json.dumps({"archive": archive.name, "bytes": archive.stat().st_size, "sha256": checksum, "verification": "OK"}))


if __name__ == "__main__":
    main()
