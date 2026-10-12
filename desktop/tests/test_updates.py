"""Updates through the shared installer: what belongs to gpx2elev.

The protocol (download, checks, helper, rollback) is tested in nico579_commons
(maj_install). Here: gpx2elev's bundle and archives, its self-test, the restart
arguments, the page, and the folders left by the updates of versions 0.3 and 0.4.
"""
import argparse
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from nico579_commons import maj_archive, maj_install

from gpx2elev import __version__, updates
from gpx2elev.__main__ import main
from gpx2elev.web import Application, serve

DESKTOP = Path(__file__).resolve().parents[1]
EXECUTABLE = "gpx2elev.exe" if sys.platform == "win32" else "gpx2elev"


def onedir():
    """A PyInstaller onedir folder (Windows, Linux) whatever the test system:
    on macOS the published bundle is an .app, another layout."""
    return patch.multiple(maj_install.platform, system=lambda: "Windows" if sys.platform == "win32" else "Linux",
                          machine=lambda: "x86_64")


def bundle(folder, *extra):
    (folder / "_internal").mkdir(parents=True)
    for name in extra:
        (folder / name).write_text("x")
    executable = folder / EXECUTABLE
    executable.write_bytes(b"x")
    return patch.object(sys, "frozen", True, create=True), patch.object(sys, "executable", str(executable))


class SelfTest(unittest.TestCase):
    def test_accepts_its_version_with_or_without_v(self):
        self.assertEqual(updates.self_test(__version__), 0)
        self.assertEqual(updates.self_test("v" + __version__), 0)

    def test_refuses_another_version_and_a_bundle_missing_page_files(self):
        self.assertEqual(updates.self_test("0.0.1"), 1)
        # A .spec that forgets the data of nico579_commons: the page would ask for
        # /nico579-maj.js and /nico579-reglages.js in vain.
        with patch("nico579_commons.serveweb.fichiers_manquants", return_value=["reglages.js"]):
            self.assertEqual(updates.self_test(__version__), 1)
        with tempfile.TemporaryDirectory() as empty, patch("gpx2elev.runtime.GUI", Path(empty)):
            self.assertEqual(updates.self_test(__version__), 1)

    def test_command_line_runs_it_before_anything_else(self):
        with patch("gpx2elev.web.serve") as served, patch("sys.stdout", io.StringIO()):
            self.assertEqual(main(["--self-test-version", __version__]), 0)
        served.assert_not_called()
        with self.assertRaises(SystemExit) as stopped, patch("sys.stderr", io.StringIO()):
            main(["--self-test-version"])
        self.assertEqual(stopped.exception.code, 2)


class Installation(unittest.TestCase):
    def test_published_bundle_is_accepted_with_its_linux_desktop_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory).resolve() / "gpx2elev-linux-x86_64"
            frozen, executable = bundle(folder, "gpx2elev.desktop")
            with frozen, executable, onedir():
                disposition = updates.disposition()
        self.assertEqual(disposition.install_root, folder)
        self.assertIn(disposition.asset_name, ("gpx2elev-windows-x86_64.zip", "gpx2elev-linux-x86_64.tar.gz"))
        self.assertEqual(disposition.expected_root, disposition.asset_name.split(".")[0])

    def test_sources_and_a_general_folder_are_never_replaced(self):
        with self.assertRaises(maj_archive.ErreurMiseAJour) as caught:
            updates.disposition()
        self.assertEqual(caught.exception.code, "source_mode")
        with tempfile.TemporaryDirectory() as directory:
            frozen, executable = bundle(Path(directory).resolve() / "Downloads", "photo.jpg")
            with frozen, executable, onedir(), self.assertRaises(maj_archive.ErreurMiseAJour) as caught:
                updates.disposition()
        self.assertEqual(caught.exception.code, "unsafe_install")

    def test_archive_names_of_the_four_published_systems(self):
        for system, machine, expected in (("Windows", "AMD64", "gpx2elev-windows-x86_64.zip"),
                                          ("Linux", "x86_64", "gpx2elev-linux-x86_64.tar.gz"),
                                          ("Darwin", "arm64", "gpx2elev-macos-arm64.zip"),
                                          ("Darwin", "x86_64", "gpx2elev-macos-x86_64.zip")):
            with self.subTest(system=system), patch.multiple(maj_install.platform, system=lambda: system,
                                                             machine=lambda: machine):
                name, _, root = maj_install.archive_standard("gpx2elev", racine_macos="gpx2elev.app")
                self.assertEqual((name, root), (expected, "gpx2elev.app" if system == "Darwin" else expected.split(".")[0]))


class Restart(unittest.TestCase):
    def serve(self, **options):
        """Run serve() until its application has a port, then end it as the installer does."""
        created = []

        class Recording(Application):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                created.append(self)

        with tempfile.TemporaryDirectory() as directory:
            values = dict(data_dir=Path(directory), port=0, new_instance=True, gpx=None, offline=True, model=None,
                          no_browser=True, no_tray=True, update_result=None)
            values.update(options)
            with patch("gpx2elev.web.Application", Recording), patch("webbrowser.open") as opened,                     patch("sys.stdout", io.StringIO()):
                thread = threading.Thread(target=serve, args=(argparse.Namespace(**values),))
                thread.start()
                deadline = time.monotonic() + 10
                while not (created and "--port" in created[0].relaunch) and time.monotonic() < deadline:
                    time.sleep(.01)
                installer = created[0].installer
                [arguments] = maj_install.processus_a_relancer(installer.app, installer.verbes_relance())
                installer.quitter()  # What the installer calls once its helper is ready.
                thread.join(10)
                self.assertFalse(thread.is_alive())
            return arguments, str(Path(directory).resolve()), opened.call_count

    def test_new_version_reuses_the_data_and_the_port(self):
        arguments, directory, _ = self.serve()
        self.assertEqual(arguments[:3], ["--data-dir", directory, "--port"])
        self.assertTrue(arguments[3].isdigit())
        self.assertEqual(arguments[4:], ["--no-browser", "--no-tray"])

    def test_the_tab_opened_at_start_reloads_instead_of_a_second_one(self):
        arguments, _, opened = self.serve(no_browser=False)
        self.assertEqual(opened, 1)
        self.assertEqual(arguments[4:], ["--no-tray", "--no-browser"])


class LegacyLeftovers(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.install = self.root / "gpx2elev"
        self.install.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def work(self, name, target, finished=True):
        work = self.root / name
        for folder in ("previous/_internal", "helper/gpx2elev/_internal"):
            (work / folder).mkdir(parents=True)
        (work / "previous" / EXECUTABLE).write_bytes(b"old version")
        (work / "plan.json").write_text(json.dumps({"target": str(target)}))
        if finished:
            (work / "result.json").write_text(json.dumps({"status": "OK"}))
        return work

    def test_only_finished_updates_of_this_installation_are_removed(self):
        done = self.work(".gpx2elev-update-a1", self.install)
        other = self.work(".gpx2elev-update-b2", self.root / "other" / "gpx2elev")
        pending = self.work(".gpx2elev-update-c3", self.install, finished=False)
        self.assertEqual(updates.remove_legacy_updates(self.install), [done])
        self.assertFalse(done.exists())
        self.assertTrue(other.exists() and pending.exists() and self.install.exists())

    def test_a_locked_file_keeps_the_markers_and_the_next_start_finishes(self):
        done = self.work(".gpx2elev-update-a1", self.install)
        with patch("shutil.rmtree", side_effect=PermissionError("locked")):
            self.assertEqual(updates.remove_legacy_updates(self.install), [])
        self.assertTrue((done / "plan.json").is_file() and (done / "result.json").is_file())
        self.assertEqual(updates.remove_legacy_updates(self.install), [done])


class Page(unittest.TestCase):
    def test_page_loads_the_common_banner_and_settings_after_the_application(self):
        html = (DESKTOP / "gpx2elev/assets/web/index.html").read_text(encoding="utf-8")
        for script in ("/nico579-maj.js", "/nico579-reglages.js"):
            self.assertIn(f'<script defer src="{script}"></script>', html)
            self.assertLess(html.index("/app.js"), html.index(script))
        # The settings button sits just before FR / EN, as in the other applications.
        self.assertLess(html.index('id="nico579-reglages"'), html.index("data-nico579-langue"))

    def test_bundles_carry_the_common_page_files(self):
        self.assertIn('collect_data_files("nico579_commons")', (DESKTOP / "bundle.spec").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
