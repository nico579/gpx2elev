"""Manual updates from the official releases, with verified downloads and rollback."""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import zipfile

import requests

from . import __version__

REPOSITORY = "https://github.com/nico579/gpx2elev"
LATEST_URL = "https://api.github.com/repos/nico579/gpx2elev/releases/latest"
MAX_DOWNLOAD = 512 * 1024 * 1024
MAX_EXPANDED = 2 * 1024 * 1024 * 1024
_PROCESS_LAUNCH_LOCK = threading.Lock()


class UpdateError(Exception):
    pass


class UpdateCancelled(Exception):
    pass


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", value):
        raise UpdateError("Version de mise à jour invalide.")
    return tuple(int(n) for n in value.removeprefix("v").split("."))


def platform_name(system=None, machine=None):
    system = system or sys.platform
    machine = (machine or platform.machine()).lower()
    names = {"win32": "windows", "darwin": "macos", "linux": "linux"}
    arch = {"amd64": "x64", "x86_64": "x64", "x64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(machine)
    if system not in names or arch is None or (system != "darwin" and arch != "x64"):
        raise UpdateError("Aucune mise à jour disponible pour ce système.")
    return f"{names[system]}-{arch}"


@dataclass(frozen=True)
class Release:
    version: str
    tag: str
    name: str
    url: str
    size: int
    sha256: str | None
    notes: str
    checksum_url: str | None = None


def parse_release(data, target, current=__version__):
    if not isinstance(data, dict) or data.get("draft") is not False or data.get("prerelease") is not False:
        raise UpdateError("Réponse de mise à jour invalide.")
    tag = data.get("tag_name")
    version = version_tuple(tag)
    if version <= version_tuple(current):
        return None
    version_text = tag.removeprefix("v")
    suffix = "tar.gz" if target == "linux-x64" else "zip"
    name = f"gpx2elev-{version_text}-{target}.{suffix}"
    assets = data.get("assets")
    if not isinstance(assets, list):
        raise UpdateError("Réponse de mise à jour invalide.")
    matches = [a for a in assets if isinstance(a, dict) and a.get("name") == name]
    if len(matches) != 1:
        raise UpdateError("Le fichier de mise à jour de ce système est absent.")
    asset = matches[0]
    url = f"{REPOSITORY}/releases/download/{tag}/{name}"
    if asset.get("browser_download_url") != url or type(asset.get("size")) is not int or not 0 < asset["size"] <= MAX_DOWNLOAD:
        raise UpdateError("Réponse de mise à jour invalide.")
    digest = asset.get("digest")
    sha256 = None
    if digest is not None:
        if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
            raise UpdateError("Empreinte de mise à jour invalide.")
        sha256 = digest[7:].lower()
    checksum_url = f"{REPOSITORY}/releases/download/{tag}/SHA256SUMS.txt"
    if sha256 is None and not any(isinstance(a, dict) and a.get("name") == "SHA256SUMS.txt" and
                                  a.get("browser_download_url") == checksum_url for a in assets):
        raise UpdateError("Empreinte de mise à jour absente.")
    return Release(version_text, tag, name, url, asset["size"], sha256,
                   str(data.get("body") or "")[:20000], checksum_url if sha256 is None else None)


def _cancelled(cancel):
    if cancel is not None and cancel.is_set():
        raise UpdateCancelled()


class UpdateClient:
    def __init__(self, cancel=None, session=None):
        self.cancel = cancel
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": f"gpx2elev/{__version__}", "Accept-Encoding": "identity"})

    def close(self):
        self.session.close()

    def _open(self, url):
        # Follow only GitHub's HTTPS asset redirects; never accept an HTTP downgrade.
        from urllib.parse import urlsplit, urljoin
        for _ in range(6):
            _cancelled(self.cancel)
            parsed = urlsplit(url)
            if parsed.scheme != "https" or parsed.hostname not in {
                "api.github.com", "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"
            } or parsed.username is not None or parsed.password is not None or parsed.port not in (None, 443):
                raise UpdateError("Adresse de mise à jour invalide.")
            response = self.session.get(url, timeout=(15, 30), stream=True, allow_redirects=False,
                                        headers={"Accept": "application/vnd.github+json" if url == LATEST_URL else "application/octet-stream"})
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                response.close()
                if not location:
                    break
                url = urljoin(url, location)
                continue
            if response.status_code != 200:
                code = response.status_code
                response.close()
                if code in (403, 429):
                    raise UpdateError("GitHub limite les vérifications. Réessayez plus tard.")
                if code == 404 and url == LATEST_URL:
                    raise UpdateError("Aucune release publiée pour le moment.")
                raise UpdateError("Le serveur de mises à jour est indisponible.")
            return response
        raise UpdateError("Adresse de mise à jour invalide.")

    def _bytes(self, url, limit):
        data = bytearray()
        with self._open(url) as response:
            for chunk in response.iter_content(65536):
                _cancelled(self.cancel)
                data.extend(chunk)
                if len(data) > limit:
                    raise UpdateError("Réponse de mise à jour trop volumineuse.")
        return bytes(data)

    def check(self, target=None, current=__version__):
        try:
            data = json.loads(self._bytes(LATEST_URL, 1024 * 1024))
        except (ValueError, UnicodeError) as exc:
            raise UpdateError("Réponse de mise à jour invalide.") from exc
        return parse_release(data, target or platform_name(), current)

    def download(self, release, directory, progress=lambda done, total: None):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        expected = release.sha256
        if expected is None:
            try:
                lines = self._bytes(release.checksum_url, 65536).decode("utf-8").splitlines()
            except UnicodeError as exc:
                raise UpdateError("Empreinte de mise à jour invalide.") from exc
            values = [m.group(1).lower() for line in lines
                      if (m := re.fullmatch(r"([0-9a-fA-F]{64})  (.+)", line)) and m.group(2) == release.name]
            if len(values) != 1:
                raise UpdateError("Empreinte de mise à jour absente.")
            expected = values[0]
        final = directory / release.name
        fd, temporary_name = tempfile.mkstemp(prefix="download-", suffix=".part", dir=directory)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "wb") as output, self._open(release.url) as response:
                checksum, count = hashlib.sha256(), 0
                for chunk in response.iter_content(65536):
                    _cancelled(self.cancel)
                    count += len(chunk)
                    if count > release.size:
                        raise UpdateError("Fichier de mise à jour incomplet ou corrompu.")
                    output.write(chunk)
                    checksum.update(chunk)
                    progress(count, release.size)
            _cancelled(self.cancel)
            if count != release.size or checksum.hexdigest() != expected:
                raise UpdateError("Fichier de mise à jour incomplet ou corrompu.")
            os.replace(temporary, final)
            return final
        finally:
            temporary.unlink(missing_ok=True)


def bundle_binary(root, system=None):
    system = system or sys.platform
    return Path(root) / ({"win32": "gpx2elev.exe", "darwin": "Contents/MacOS/gpx2elev"}.get(system, "gpx2elev"))


def installed_bundle(executable=None, frozen=None, system=None):
    if not (getattr(sys, "frozen", False) if frozen is None else frozen):
        return None
    system = system or sys.platform
    executable = Path(executable or sys.executable).resolve()
    root = executable.parents[2] if system == "darwin" else executable.parent
    expected_name = "gpx2elev.app" if system == "darwin" else "gpx2elev"
    if root.name != expected_name or bundle_binary(root, system) != executable:
        return None
    return root


def _member_path(name, root_name):
    path = PurePosixPath(name)
    if "\\" in name or path.is_absolute() or any(p in ("..", ".") or ":" in p for p in path.parts) or not path.parts:
        raise UpdateError("Archive de mise à jour invalide.")
    # Apple's ditto includes resource forks alongside the .app; they are not executable content.
    if path.parts[0] == "__MACOSX":
        return None
    if path.parts[0] != root_name:
        raise UpdateError("Archive de mise à jour invalide.")
    return path


def extract_bundle(archive, destination, system=None, cancel=None):
    """Extract bounded, regular files; restore only internal symlinks after all files."""
    system = system or sys.platform
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    root_name = "gpx2elev.app" if system == "darwin" else "gpx2elev"
    links, entries, total = [], set(), 0

    def member(name, size):
        nonlocal total
        _cancelled(cancel)
        total += size
        if total > MAX_EXPANDED or len(entries) >= 30000 or size < 0:
            raise UpdateError("Archive de mise à jour trop volumineuse.")
        relative = _member_path(name, root_name)
        if relative is None:
            return None
        path = destination.joinpath(*relative.parts)
        if path in entries:
            raise UpdateError("Archive de mise à jour invalide.")
        entries.add(path)
        return path

    def write(path, source, size, mode):
        path.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with path.open("xb") as output:
            while chunk := source.read(65536):
                _cancelled(cancel)
                count += len(chunk)
                if count > size:
                    raise UpdateError("Archive de mise à jour invalide.")
                output.write(chunk)
        if count != size:
            raise UpdateError("Archive de mise à jour invalide.")
        path.chmod(0o755 if mode & 0o111 else 0o644)

    if system == "linux":
        with tarfile.open(archive, "r:gz") as source:
            for entry in source:
                path = member(entry.name, entry.size)
                if path is None:
                    continue
                if entry.isdir():
                    path.mkdir(parents=True, exist_ok=True)
                elif entry.issym():
                    links.append((path, entry.linkname))
                elif entry.isfile():
                    with source.extractfile(entry) as content:
                        write(path, content, entry.size, entry.mode)
                else:
                    raise UpdateError("Archive de mise à jour invalide.")
    else:
        with zipfile.ZipFile(archive) as source:
            for entry in source.infolist():
                path = member(entry.filename, entry.file_size)
                if path is None:
                    continue
                mode = entry.external_attr >> 16
                if entry.is_dir():
                    path.mkdir(parents=True, exist_ok=True)
                elif stat.S_ISLNK(mode):
                    if system != "darwin" or entry.file_size > 4096:
                        raise UpdateError("Archive de mise à jour invalide.")
                    links.append((path, source.read(entry).decode("utf-8")))
                elif stat.S_IFMT(mode) not in (0, stat.S_IFREG):
                    raise UpdateError("Archive de mise à jour invalide.")
                else:
                    with source.open(entry) as content:
                        write(path, content, entry.file_size, mode)
    root = destination / root_name
    for path, target in links:
        if not target or "\\" in target or Path(target).is_absolute() or not (path.parent / target).resolve().is_relative_to(root):
            raise UpdateError("Archive de mise à jour invalide.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(target)
    # A symlink chain may resolve outside the bundle once all links exist.
    if any(not path.resolve().is_relative_to(root) for path, _ in links):
        raise UpdateError("Archive de mise à jour invalide.")
    binary = bundle_binary(root, system)
    if not binary.is_file() or binary.is_symlink() or (system != "win32" and not os.access(binary, os.X_OK)):
        raise UpdateError("Le programme de mise à jour est absent de l'archive.")
    return root


def verify_bundle(root, report, expected_version=None, cancel=None):
    process = _launch([str(bundle_binary(root)), "--self-test-report", str(report)], root, {"QT_QPA_PLATFORM": "offscreen"})
    try:
        deadline = time.monotonic() + 90
        while process.poll() is None:
            _cancelled(cancel)
            if time.monotonic() > deadline:
                raise UpdateError("Le programme téléchargé n'a pas réussi sa vérification.")
            time.sleep(.1)
        try:
            result = json.loads(Path(report).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise UpdateError("Le programme téléchargé n'a pas réussi sa vérification.") from exc
        if process.returncode != 0 or result.get("status") != "OK" or (expected_version is not None and result.get("version") != expected_version):
            raise UpdateError("Le programme téléchargé n'a pas réussi sa vérification.")
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()


def prepare_install(archive, target, data_dir, cancel=None, expected_version=None):
    """Keep the old installation untouched until the UI exits and a separate helper applies it."""
    target = Path(target).resolve()
    if Path(data_dir).resolve().is_relative_to(target):
        raise UpdateError("Le dossier de données doit être situé hors du dossier de l'application pour la mise à jour.")
    work = Path(tempfile.mkdtemp(prefix=".gpx2elev-update-", dir=target.parent))
    try:
        new_root = extract_bundle(archive, work / "new", cancel=cancel)
        verify_bundle(new_root, work / "verification.json", expected_version, cancel)
        _cancelled(cancel)
        # Running from a copy avoids locking either the installed or the replacement files on Windows.
        helper = work / "helper" / target.name
        shutil.copytree(target, helper, symlinks=True)
        _cancelled(cancel)
        plan = work / "plan.json"
        plan.write_text(json.dumps({"target": str(target), "work": str(work), "data": str(Path(data_dir).resolve()),
                                    "parent": os.getpid(), "system": sys.platform}), encoding="utf-8")
        return plan
    except BaseException:
        shutil.rmtree(work)
        raise


def _plan(plan):
    plan = Path(plan).resolve()
    data = json.loads(plan.read_text(encoding="utf-8"))
    work, target = Path(data["work"]), Path(data["target"])
    system = data["system"]
    name = "gpx2elev.app" if system == "darwin" else "gpx2elev"
    if (system not in ("win32", "linux", "darwin") or not work.is_absolute() or not target.is_absolute()
        or work.resolve() != work or target.resolve() != target or plan != work / "plan.json"
        or not work.name.startswith(".gpx2elev-update-") or work.parent != target.parent or target.name != name
        or Path(data["data"]).resolve().is_relative_to(target) or type(data["parent"]) is not int or data["parent"] <= 0):
        raise UpdateError("Plan de mise à jour invalide.")
    return data, work, target


def launch_helper(plan):
    data, work, target = _plan(plan)
    binary = bundle_binary(work / "helper" / target.name, data["system"])
    return _launch([str(binary), "--apply-update", str(plan)], binary.parent)


def discard_install(plan):
    _, work, _ = _plan(plan)
    if (work / "ready").exists() or (work / "result.json").exists():
        raise UpdateError("Une installation déjà lancée ne peut pas être annulée.")
    shutil.rmtree(work)


def _subprocess_environment():
    environment = os.environ.copy()
    environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    if getattr(sys, "frozen", False):
        for key in ("LD_LIBRARY_PATH", "LIBPATH"):
            original = environment.get(key + "_ORIG")
            if original is None:
                environment.pop(key, None)
            else:
                environment[key] = original
        root = installed_bundle() or Path(sys._MEIPASS).resolve()
        for key in ("PATH", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "GDAL_DATA", "PROJ_LIB", "PROJ_DATA"):
            if key in environment:
                paths = [p for p in environment[key].split(os.pathsep) if p and not Path(p).resolve().is_relative_to(root)]
                if paths:
                    environment[key] = os.pathsep.join(paths)
                else:
                    environment.pop(key)
    return environment


def _launch(arguments, cwd, overrides=None):
    environment = _subprocess_environment()
    environment.update(overrides or {})

    def spawn():
        return subprocess.Popen(arguments, cwd=cwd, env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=sys.platform != "win32",
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)

    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return spawn()
    # The Windows DLL search directory is inherited too; restore it immediately for this process.
    import ctypes
    with _PROCESS_LAUNCH_LOCK:
        ctypes.windll.kernel32.SetDllDirectoryW(None)
        try:
            return spawn()
        finally:
            ctypes.windll.kernel32.SetDllDirectoryW(str(sys._MEIPASS))


def _parent_running(pid):
    if sys.platform == "win32":
        import ctypes
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.restype = ctypes.c_void_p
        handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if not handle:
            return False
        try:
            kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            return kernel.WaitForSingleObject(handle, 0) == 258  # WAIT_TIMEOUT
        finally:
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def apply_install(plan, wait=True, restart=True):
    """Private frozen entry point: wait for shutdown, swap, then launch; rollback on failure."""
    data, work, target = _plan(plan)
    replacement = work / "new" / target.name
    backup = work / "previous"
    if not bundle_binary(replacement, data["system"]).is_file() or backup.exists():
        raise UpdateError("Plan de mise à jour invalide.")
    if wait:
        deadline = time.monotonic() + 120
        while not (work / "ready").exists() or _parent_running(data["parent"]):
            if time.monotonic() > deadline:
                return 1  # The application never exited: leave the installation untouched.
            time.sleep(.25)
    swapped = False
    try:
        # Antivirus scanners can briefly retain a file after the process exits.
        deadline = time.monotonic() + 15
        while True:
            try:
                target.rename(backup)
                break
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.25)
        replacement.rename(target)
        swapped = True
        result = {"status": "OK", "backup": str(backup)}
        (work / "result.json").write_text(json.dumps(result), encoding="utf-8")
        if restart:
            process = _launch([str(bundle_binary(target, data["system"])), "--data-dir", data["data"],
                              "--update-result", str(work / "result.json")], target)
            time.sleep(1)
            if process.poll() not in (None, 0):
                raise UpdateError("Le programme téléchargé n'a pas réussi sa vérification.")
            result["pid"] = process.pid
            (work / "result.json").write_text(json.dumps(result), encoding="utf-8")
        return 0
    except Exception as exc:
        if swapped:
            target.rename(replacement)
        if backup.exists() and not target.exists():
            backup.rename(target)
        (work / "result.json").write_text(json.dumps({"status": "ERROR", "error": str(exc)}), encoding="utf-8")
        if restart and bundle_binary(target, data["system"]).is_file():
            _launch([str(bundle_binary(target, data["system"])), "--data-dir", data["data"],
                     "--update-result", str(work / "result.json")], target)
        return 1
