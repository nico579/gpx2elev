import argparse
import json
import os
from pathlib import Path
import sys

from . import __version__


def main(argv=None):
    parser = argparse.ArgumentParser(description="gpx2elev : estimation du dénivelé d'un GPX")
    parser.add_argument("gpx", nargs="?", help="GPX à ouvrir")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--calculate", action="store_true", help="Calcul sans interface graphique")
    parser.add_argument("--offline", action="store_true", help="Utiliser uniquement les profils en cache")
    parser.add_argument("--model", choices=["IGN", "MAPTERHORN", "FABDEM", "COPERNICUS", "SRTM"], help="Forcer un modèle au lieu du repli automatique")
    parser.add_argument("--data-dir", type=Path, help="Dossier de données et de cache")
    parser.add_argument("--output", type=Path, help="Résultat JSON du calcul sans interface")
    parser.add_argument("--csv", type=Path, help="Résultats CSV du calcul sans interface")
    parser.add_argument("--self-test-report", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--apply-update", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--update-result", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.apply_update:
        from .updates import apply_install
        return apply_install(args.apply_update)
    if args.self_test_report:
        # No display server is required for the automated packaged GUI check.
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from .smoke import run_smoke
            return run_smoke(args.self_test_report)
        except Exception:
            import traceback
            args.self_test_report.parent.mkdir(parents=True, exist_ok=True)
            args.self_test_report.write_text(json.dumps({"status": "ERROR", "traceback": traceback.format_exc()}, ensure_ascii=False, indent=2), encoding="utf-8")
            return 1
    if args.calculate:
        if not args.gpx:
            parser.error("--calculate demande un fichier GPX")
        from PySide6.QtCore import QCoreApplication
        from .providers import Source
        from .service import calculate, export_json, export_summary
        from .ui import data_directory
        core_app = QCoreApplication.instance() or QCoreApplication(["gpx2elev"])
        core_app.setApplicationName("gpx2elev")
        core_app.setOrganizationName("Nico")
        try:
            result = calculate(args.gpx, args.data_dir or data_directory(), not args.offline, Source[args.model] if args.model else None)
            if args.output:
                export_json(result, args.output)
            if args.csv:
                export_summary(result, args.csv)
            if sys.stdout is not None:
                print(json.dumps(result.summary(), ensure_ascii=False, indent=2))
            return 0
        except Exception as exc:
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps({"erreur": str(exc)}, ensure_ascii=False), encoding="utf-8")
            if sys.stderr is not None:
                print(str(exc), file=sys.stderr)
            return 2
    from .providers import Source
    from .ui import DesktopApplication, MainWindow
    from PySide6.QtCore import QTimer
    app = DesktopApplication(sys.argv if argv is None else ["gpx2elev"] + argv)
    window = MainWindow(args.data_dir, restore=not (args.gpx or app.pending_path))
    app.window = window
    if args.offline:
        window.online.setChecked(False)
    if args.model:
        window.models.setCurrentIndex(window.models.findData(Source[args.model]))
    path = args.gpx or app.pending_path
    if path:
        QTimer.singleShot(0, lambda: window.open_path(path))
    window.show()
    if args.update_result:
        try:
            installed = json.loads(args.update_result.read_text(encoding="utf-8"))
            if installed.get("status") == "ERROR":
                from PySide6.QtWidgets import QMessageBox
                QTimer.singleShot(0, lambda: QMessageBox.warning(window, window.tr("Mises à jour"),
                    window.tr("La mise à jour a échoué. L'ancienne version a été restaurée.")))
        except (OSError, ValueError):
            pass
    code = app.exec()
    if window.pending_update is not None:
        # The helper also waits for this process to terminate, releasing all bundled DLLs.
        (window.pending_update.parent / "ready").write_text("ready", encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
