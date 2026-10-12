"""Desktop updates through the shared installer of nico579-commons.

nico579_commons.maj_install downloads the archive of the latest release, checks
its SHA-256 and contents, runs the new bundle's --self-test-version, then an
external helper swaps the folders once gpx2elev has exited and restarts it; on
any failure it puts the previous version back. This module only describes
gpx2elev: its archives, the files its bundle may hold and its self-test.
"""
from pathlib import Path
import shutil
import sys

from nico579_commons import atomique, maj_install

from . import __version__

REPOSITORY = "nico579/gpx2elev"
# The Linux bundle carries its desktop entry next to the executable.
TOLERATED = ("gpx2elev.desktop",)
# Versions 0.3 and 0.4 updated themselves through this work folder, next to the
# installation, and never removed it: it keeps the whole previous version.
LEGACY_PREFIX = ".gpx2elev-update-"
PAGE = ("index.html", "app.js", "chart.js", "style.css", "web_bridge.js")


def _say(text):
    if sys.stdout is not None:
        print(text, flush=True)


def application():
    return maj_install.Application("gpx2elev", noms_toleres=TOLERATED)


def disposition():
    """This bundle's installation folder and the archive that replaces it.

    Raises ErreurMiseAJour from sources and for any folder that is not the
    published bundle, such as a Downloads folder holding other files."""
    name, kind, root = maj_install.archive_standard("gpx2elev", racine_macos="gpx2elev.app")
    return maj_install.disposition(application(), asset_name=name, archive_kind=kind, racine_attendue=root)


def installer(checker, quit, arguments):
    """The installation conducted in the background for the tray menu and the page.

    `arguments` returns the restart arguments, known once the server has its port."""
    return maj_install.Installateur(application(), REPOSITORY, checker, disposition, quitter=quit,
                                    verbes_relance=lambda: [arguments()])


def self_test(expected):
    """`--self-test-version X`, run by the installer on a downloaded bundle before
    anything is replaced: 0 if this program is version X and can serve its page."""
    try:
        from nico579_commons import serveweb
        from . import web  # noqa: F401  The page server and all its dependencies.
        from .runtime import GUI
        missing = serveweb.fichiers_manquants() + [name for name in PAGE if not (GUI / name).is_file()]
    except Exception as exc:
        _say(f"auto-test : {type(exc).__name__}: {exc}")
        return 1
    if missing:
        _say("auto-test : fichiers absents du bundle : " + ", ".join(missing))
        return 1
    if __version__ != expected.lstrip("vV"):
        _say(f"auto-test : version {__version__}, attendue {expected}")
        return 1
    _say(f"gpx2elev {__version__}")
    return 0


def remove_legacy_updates(root):
    """Remove the work folders of finished 0.3/0.4 updates of this installation.

    Each one holds the whole previous version and a copy of the old helper. Only
    a folder whose plan targets `root` and whose result was written is touched.
    Its plan and result go last: a file still locked keeps them, and the next
    start tries again."""
    root = Path(root).resolve()
    removed = []
    for work in root.parent.glob(LEGACY_PREFIX + "*"):
        plan = atomique.lire_json(work / "plan.json", None)
        target = plan.get("target") if isinstance(plan, dict) else None
        if not isinstance(target, str) or Path(target).resolve() != root or not (work / "result.json").is_file():
            continue
        markers = ("plan.json", "result.json")
        try:
            for item in work.iterdir():
                if item.name in markers:
                    continue
                if item.is_dir() and not item.is_symlink():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            for name in markers:
                (work / name).unlink()
            work.rmdir()
        except OSError:
            continue
        removed.append(work)
    return removed
