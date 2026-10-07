import hashlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import tarfile
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from gpx2elev.updates import (LATEST_URL, REPOSITORY, Release, UpdateCancelled, UpdateClient, UpdateError,
    apply_install, bundle_binary, discard_install, extract_bundle, installed_bundle, parse_release, platform_name, prepare_install, version_tuple)
from gpx2elev.updates import _subprocess_environment


def metadata(target="windows-x64", version="0.4.0", contents=b"verified"):
    tag = "v" + version
    name = f"gpx2elev-{version}-{target}." + ("tar.gz" if target == "linux-x64" else "zip")
    asset = {"name": name, "browser_download_url": f"{REPOSITORY}/releases/download/{tag}/{name}",
             "size": len(contents), "digest": "sha256:" + hashlib.sha256(contents).hexdigest()}
    return {"tag_name": tag, "draft": False, "prerelease": False, "assets": [asset], "body": "New release"}


class Response:
    def __init__(self, contents, status=200, headers=None):
        self.contents, self.status_code, self.headers = contents, status, headers or {}
        self.closed = False

    def iter_content(self, size):
        yield self.contents[:2]
        yield self.contents[2:]

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class Session:
    def __init__(self, responses):
        self.responses, self.headers, self.urls = iter(responses), {}, []

    def get(self, url, **kwargs):
        self.urls.append(url)
        return next(self.responses)

    def close(self):
        pass


def zip_bundle(path, system="win32", extra=()):
    name = "gpx2elev.app/Contents/MacOS/gpx2elev" if system == "darwin" else "gpx2elev/gpx2elev.exe"
    with zipfile.ZipFile(path, "w") as out:
        entry = zipfile.ZipInfo(name)
        entry.external_attr = (stat.S_IFREG | 0o755) << 16
        out.writestr(entry, b"new binary")
        for entry, content in extra:
            out.writestr(entry, content)


class UpdateTests(unittest.TestCase):
    def test_restarted_bundle_does_not_inherit_the_previous_libraries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundled, external = root / "bundle", root / "system"
            environment = {"LD_LIBRARY_PATH": str(bundled), "LD_LIBRARY_PATH_ORIG": str(external),
                "PATH": os.pathsep.join((str(bundled / "plugins"), str(external))),
                "QT_PLUGIN_PATH": str(bundled / "plugins"), "GDAL_DATA": str(bundled / "gdal"), "QT_QPA_PLATFORM": "offscreen"}
            with patch.dict(os.environ, environment, clear=True), patch("sys.frozen", True, create=True), \
                 patch("sys._MEIPASS", str(bundled), create=True), patch("gpx2elev.updates.installed_bundle", return_value=bundled.resolve()):
                prepared = _subprocess_environment()
                self.assertEqual(os.environ["QT_PLUGIN_PATH"], str(bundled / "plugins"))
            self.assertEqual(prepared["PYINSTALLER_RESET_ENVIRONMENT"], "1")
            self.assertEqual(prepared["LD_LIBRARY_PATH"], str(external))
            self.assertEqual(prepared["PATH"], str(external))
            self.assertEqual(prepared["QT_QPA_PLATFORM"], "offscreen")
            self.assertNotIn("QT_PLUGIN_PATH", prepared)
            self.assertNotIn("GDAL_DATA", prepared)

    def test_version_and_all_platform_selections_no_downgrade(self):
        self.assertGreater(version_tuple("v0.10.0"), version_tuple("0.9.9"))
        for bad in (None, "v0.3.3-beta", "0.03.4", "../0.4.0", "0.4"):
            with self.assertRaises(UpdateError):
                version_tuple(bad)
        for system, machine, target in (("win32", "AMD64", "windows-x64"), ("linux", "x86_64", "linux-x64"),
                                         ("darwin", "aarch64", "macos-arm64"), ("darwin", "x86_64", "macos-x64")):
            self.assertEqual(platform_name(system, machine), target)
            self.assertEqual(parse_release(metadata(target), target, "0.3.3").version, "0.4.0")
        self.assertIsNone(parse_release(metadata(version="0.3.3"), "windows-x64", "0.3.3"))
        self.assertIsNone(parse_release(metadata(version="0.3.2"), "windows-x64", "0.3.3"))
        with self.assertRaises(UpdateError):
            platform_name("win32", "ARM64")

    def test_rejects_untrusted_missing_and_ambiguous_assets(self):
        for mutation in (lambda j: j.update(draft=True), lambda j: j.update(prerelease=True),
                         lambda j: j["assets"][0].update(browser_download_url="https://example.com/program.exe"),
                         lambda j: j["assets"][0].update(size=0),
                         lambda j: j["assets"][0].update(digest="sha256:bad"),
                         lambda j: j["assets"].append(j["assets"][0].copy()),
                         lambda j: j["assets"][0].pop("digest")):
            data = metadata()
            mutation(data)
            with self.assertRaises(UpdateError):
                parse_release(data, "windows-x64", "0.3.3")

    def test_verified_download_checksum_fallback_and_size_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = b"verified"
            release = parse_release(metadata(contents=payload), "windows-x64", "0.3.3")
            session = Session([Response(json.dumps(metadata()).encode()), Response(payload)])
            client = UpdateClient(session=session)
            self.assertEqual(client.check("windows-x64", "0.3.3"), release)
            self.assertEqual(client.download(release, directory).read_bytes(), payload)
            self.assertEqual(session.urls, [LATEST_URL, release.url])
            for corrupt in (b"wrong!!!", payload[:-1], payload + b"extra"):
                with self.assertRaises(UpdateError):
                    UpdateClient(session=Session([Response(corrupt)])).download(release, directory)
                self.assertEqual((Path(directory) / release.name).read_bytes(), payload)
                self.assertEqual(list(Path(directory).glob("*.part")), [])
            data = metadata()
            data["assets"][0]["digest"] = None
            checksums = f"{REPOSITORY}/releases/download/v0.4.0/SHA256SUMS.txt"
            data["assets"].append({"name": "SHA256SUMS.txt", "browser_download_url": checksums})
            release = parse_release(data, "windows-x64", "0.3.3")
            checksum_body = (hashlib.sha256(payload).hexdigest() + "  " + release.name + "\n").encode()
            self.assertEqual(UpdateClient(session=Session([Response(checksum_body), Response(payload)]))
                             .download(release, directory).read_bytes(), payload)

    def test_cancellation_redirect_policy_and_rate_limit(self):
        event = threading.Event()
        release = parse_release(metadata(), "windows-x64", "0.3.3")
        with tempfile.TemporaryDirectory() as directory:
            client = UpdateClient(event, Session([Response(b"verified")]))
            with self.assertRaises(UpdateCancelled):
                client.download(release, directory, lambda *args: event.set())
            self.assertEqual(list(Path(directory).iterdir()), [])
        for bad in ("http://github.com/download", "https://evil.example/download", "https://github.com@evil.example/download"):
            with self.assertRaises(UpdateError):
                UpdateClient(session=Session([Response(b"", 302, {"Location": bad})])).check()
        with self.assertRaisesRegex(UpdateError, "limite"):
            UpdateClient(session=Session([Response(b"", 429)])).check()

    def test_archive_traversal_special_files_and_internal_mac_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "update.zip"
            for i, name in enumerate(("../outside", "gpx2elev/../../outside", "C:/outside", "gpx2elev\\..\\outside")):
                entry = zipfile.ZipInfo()
                entry.filename = name  # Preserve a literal backslash, even on Windows.
                zip_bundle(archive, extra=((entry, b"bad"),))
                with self.assertRaises(UpdateError):
                    extract_bundle(archive, root / str(i), "win32")
            self.assertFalse((root / "outside").exists())
            link = zipfile.ZipInfo("gpx2elev.app/Contents/link")
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            zip_bundle(archive, "darwin", ((link, b"../../outside"),))
            with self.assertRaises(UpdateError):
                extract_bundle(archive, root / "unsafe-link", "darwin")
            zip_bundle(archive, "darwin", ((link, b"MacOS/gpx2elev"),))
            try:
                result = extract_bundle(archive, root / "safe-link", "darwin")
            except OSError as exc:
                if os.name == "nt" and getattr(exc, "winerror", None) == 1314:
                    self.skipTest("Windows symlink privilege unavailable")
                raise
            self.assertEqual((result / "Contents/link").resolve(), result / "Contents/MacOS/gpx2elev")

    def test_linux_tar_executable_and_no_external_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "update.tar.gz"
            with tarfile.open(archive, "w:gz") as out:
                entry = tarfile.TarInfo("gpx2elev/gpx2elev")
                entry.mode, entry.size = 0o755, 3
                out.addfile(entry, io.BytesIO(b"new"))
            result = extract_bundle(archive, root / "safe", "linux")
            self.assertEqual((result / "gpx2elev").read_bytes(), b"new")
            with tarfile.open(archive, "w:gz") as out:
                entry = tarfile.TarInfo("gpx2elev/escape")
                entry.type, entry.linkname = tarfile.SYMTYPE, "../../outside"
                out.addfile(entry)
            with self.assertRaises(UpdateError):
                extract_bundle(archive, root / "unsafe", "linux")

    @patch("gpx2elev.updates.verify_bundle")
    def test_install_preserves_data_waits_swaps_and_rolls_back_failure(self, verify):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            target = root / ("gpx2elev.app" if sys.platform == "darwin" else "gpx2elev")
            binary = bundle_binary(target)
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b"old binary")
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "last.gpx").write_bytes(b"user track")
            archive = root / "update.zip"
            if sys.platform in ("win32", "darwin"):
                zip_bundle(archive, sys.platform)
            else:
                archive = root / "update.tar.gz"
                with tarfile.open(archive, "w:gz") as out:
                    entry = tarfile.TarInfo("gpx2elev/gpx2elev")
                    entry.mode, entry.size = 0o755, 10
                    out.addfile(entry, io.BytesIO(b"new binary"))
            plan = prepare_install(archive, target, data_dir)
            self.assertEqual(binary.read_bytes(), b"old binary")
            self.assertEqual(apply_install(plan, wait=False, restart=False), 0)
            self.assertEqual(binary.read_bytes(), b"new binary")
            self.assertEqual((plan.parent / "previous" / binary.relative_to(target)).read_bytes(), b"old binary")
            self.assertEqual((data_dir / "last.gpx").read_bytes(), b"user track")
            plan = prepare_install(archive, target, data_dir)
            binary.write_bytes(b"rollback original")
            with patch("gpx2elev.updates._launch", side_effect=[OSError("cannot launch"), None]):
                self.assertEqual(apply_install(plan, wait=False), 1)
            self.assertEqual(binary.read_bytes(), b"rollback original")
            self.assertEqual(json.loads((plan.parent / "result.json").read_text())["status"], "ERROR")
            plan = prepare_install(archive, target, data_dir)
            discard_install(plan)
            self.assertFalse(plan.parent.exists())
            self.assertEqual(binary.read_bytes(), b"rollback original")
            self.assertEqual((data_dir / "last.gpx").read_bytes(), b"user track")
            with self.assertRaises(UpdateError):
                prepare_install(archive, target, target / "user-data")

    def test_bundle_detection_and_install_plan_path_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "gpx2elev"
            self.assertIsNone(installed_bundle(target / "gpx2elev.exe", frozen=False, system="win32"))
            self.assertEqual(installed_bundle(target / "gpx2elev.exe", frozen=True, system="win32"), target.resolve())
            self.assertIsNone(installed_bundle(root / "python.exe", frozen=True, system="win32"))
            work = root / ".gpx2elev-update-test"
            work.mkdir()
            plan = work / "plan.json"
            plan.write_text(json.dumps({"work": str(work), "target": str(root.parent / "outside"),
                                        "data": str(root / "data"), "parent": 123, "system": "win32"}))
            with self.assertRaises(UpdateError):
                apply_install(plan, wait=False)
