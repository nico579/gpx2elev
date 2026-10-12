import argparse
import json
from pathlib import Path
import sys

from . import __version__


def main(argv=None):
    parser = argparse.ArgumentParser(description="gpx2elev : estimation du dénivelé d'un GPX")
    parser.add_argument("gpx", nargs="?", help="GPX à ouvrir")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--calculate", action="store_true", help="Calcul sans interface graphique")
    parser.add_argument("--offline", action="store_true", help="Utiliser uniquement les profils en cache")
    parser.add_argument("--model", choices=["IGN", "MAPTERHORN", "FABDEM", "COPERNICUS", "SRTM"], help="Forcer un modèle")
    parser.add_argument("--data-dir", type=Path, help="Dossier de données et de cache")
    parser.add_argument("--output", type=Path, help="Résultat JSON du calcul sans interface")
    parser.add_argument("--csv", type=Path, help="Résultats CSV du calcul sans interface")
    parser.add_argument("--serve-gui", action="store_true", help="Interface web locale (mode par défaut)")
    parser.add_argument("--port", type=int, default=8769, help="Port web local (8769 par défaut, 0 pour un port libre)")
    parser.add_argument("--no-browser", action="store_true", help="Ne pas ouvrir le navigateur")
    parser.add_argument("--no-tray", action="store_true", help="Sans icône de notification")
    parser.add_argument("--new-instance", action="store_true", help="Nouvelle instance sur un port libre")
    parser.add_argument("--self-test-report", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--apply-update", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--update-result", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.apply_update:
        from .updates import apply_install
        return apply_install(args.apply_update)
    if args.self_test_report:
        try:
            from .smoke import run_smoke
            return run_smoke(args.self_test_report)
        except Exception:
            import traceback
            args.self_test_report.parent.mkdir(parents=True, exist_ok=True)
            args.self_test_report.write_text(json.dumps({"status": "ERROR", "traceback": traceback.format_exc()},
                                                       ensure_ascii=False, indent=2), encoding="utf-8")
            return 1
    if args.calculate:
        if not args.gpx:
            parser.error("--calculate demande un fichier GPX")
        from .providers import Source
        from .runtime import data_directory
        from .service import calculate, export_json, export_summary
        try:
            result = calculate(args.gpx, args.data_dir or data_directory(), not args.offline,
                               Source[args.model] if args.model else None)
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
    if args.port < 0 or args.port > 65535:
        parser.error("--port doit être compris entre 0 et 65535")
    from .web import serve
    try:
        return serve(args)
    except (OSError, ValueError) as exc:
        if sys.stderr is not None:
            print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
