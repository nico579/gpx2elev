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
import tempfile
import zipfile

from nico579_commons import maj_archive, maj_install

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gpx2elev import __version__  # noqa: E402


def run(args, **kwargs):
    subprocess.run(args, check=True, cwd=ROOT, **kwargs)


def licenses_and_icons():
    from PIL import Image
    assets = ROOT / "build/assets"
    licenses = assets / "licenses"
    licenses.mkdir(parents=True, exist_ok=True)
    icon = ROOT / "gpx2elev/assets/gpx2elev.png"
    shutil.copy2(icon, assets / "icon.png")
    shutil.copy2(ROOT / "gpx2elev/assets/gpx2elev.ico", assets / "icon.ico")
    with Image.open(icon) as image:
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
            # PyObjC's tests include binary modules named *_copying.so and
            # matching debug symbols. They are not license texts; collecting
            # them causes unnecessary Mach-O processing and SDK warnings.
            filename = Path(file).name.lower()
            if filename.startswith(("license", "copying", "copyright")) and Path(file).suffix.lower() not in {".py", ".pyc", ".pyd", ".so", ".dll"}:
                source = Path(distribution.locate_file(file))
                if source.is_file():
                    destination = target / str(file).replace("/", "_").replace("\\", "_")
                    shutil.copy2(source, destination)
    (licenses / "DEPENDENCIES.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    shutil.copy2(ROOT / "THIRD_PARTY.md", licenses / "THIRD_PARTY.md")
    shutil.copy2(ROOT / "LICENSE", licenses / "gpx2elev-LICENSE.txt")
    shutil.copy2(ROOT / "gpx2elev/assets/OFL.txt", licenses / "NotoSans-OFL.txt")


def main():
    for name in ("build", "dist"):
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT.resolve()):
            raise RuntimeError("Build path escapes the desktop checkout.")
        if path.exists():
            shutil.rmtree(path)
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
    run([str(binary), "--self-test-report", str(report)], env=env, timeout=90)
    if json.loads(report.read_text(encoding="utf-8"))["status"] != "OK":
        raise RuntimeError("Le bundle a échoué à sa vérification.")
    # Two archives of the same bundle. The shared installer (0.5 and later) looks for
    # the common name, gpx2elev-windows-x86_64.zip holding a folder of the same name.
    # Versions 0.3 and 0.4 look for gpx2elev-<version>-<system>-<arch>, holding
    # gpx2elev or gpx2elev.app: it is how they reach 0.5.
    name, _, folder = maj_install.archive_standard("gpx2elev", racine_macos="gpx2elev.app")
    legacy = f"gpx2elev-{__version__}-{system}-{arch}." + ("tar.gz" if system == "linux" else "zip")
    archives = (release / name, release / legacy)
    if system == "macos":
        bundle = ROOT / "dist/gpx2elev.app"
        # ditto preserves .app framework symlinks, unlike Python's zipfile. The shared
        # installer refuses the __MACOSX folder of --sequesterRsrc, which 0.3 and 0.4 skip.
        run(["ditto", "-c", "-k", "--keepParent", "dist/gpx2elev.app", str(archives[0])])
        run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", "dist/gpx2elev.app", str(archives[1])])
    else:
        bundle = ROOT / "dist/gpx2elev"
        if system == "linux":
            (bundle / "gpx2elev.desktop").write_text("[Desktop Entry]\nType=Application\nName=gpx2elev\nExec=gpx2elev %f\nTerminal=false\nCategories=Utility;Science;\nMimeType=application/gpx+xml;\n", encoding="utf-8")
        for archive, root in zip(archives, (folder, "gpx2elev")):
            if system == "windows":
                with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as output:
                    for path in sorted(bundle.rglob("*")):
                        if path.is_file():
                            output.write(path, f"{root}/{path.relative_to(bundle).as_posix()}")
            else:
                with tarfile.open(archive, "w:gz") as output:
                    output.add(bundle, arcname=root)
    # What the shared installer does with a downloaded archive before replacing
    # anything: extract it with its own checks, then run the extracted self-test.
    with tempfile.TemporaryDirectory() as directory:
        extracted = maj_archive.extraire(archives[0], Path(directory) / "archive", racine=folder)
        run([str(extracted / binary.relative_to(bundle)), "--self-test-version", __version__], timeout=60)
    sums, summary = [], []
    for archive in archives:
        checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
        sums.append(f"{checksum}  {archive.name}\n")
        summary.append({"archive": archive.name, "bytes": archive.stat().st_size, "sha256": checksum})
    (release / f"SHA256SUMS-{system}-{arch}.txt").write_text("".join(sums), encoding="utf-8", newline="\n")
    print(json.dumps({"archives": summary, "verification": "OK"}))


if __name__ == "__main__":
    main()
