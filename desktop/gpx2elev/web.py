"""Local browser GUI; HTTP, language controls and tray come from nico579-commons."""
import base64
from dataclasses import asdict
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import threading
import urllib.request

import numpy as np
from nico579_commons import atomique, environnement, langue, maj, maj_archive, maj_install, serveweb

from . import __version__, updates, obstacles
from .cache import cache_sizes, clear_cache
from .chart_data import ChartObservations
from .core import MAX_GPX_BYTES
from .i18n import CATALOG
from .providers import Cancelled, RANKING, Source, atomic_write
from .runtime import ASSETS, GUI, data_directory
from .service import calculate, export_json, export_profile, export_summary

WEB_TRANSLATIONS = json.loads((GUI / "translations.json").read_text(encoding="utf-8"))

PORT_GUI = 8769  # 8765–8768: blink2video, lidar2map, watch2notif, gpxsolar.
PORT_RANGE = 10
HOST = "127.0.0.1"


def _name(value):
    if not isinstance(value, str):
        raise ValueError("Ce fichier n'est pas un GPX.")
    name = value.replace("\\", "/").rsplit("/", 1)[-1]
    if Path(name).suffix.lower() != ".gpx" or any(ord(c) < 32 for c in name):
        raise ValueError("Ce fichier n'est pas un GPX.")
    return name


def _numbers(array):
    return [float(x) if np.isfinite(x) else None for x in array]


class Application:
    def __init__(self, directory=None, online=True, model=None):
        self.directory = Path(directory or data_directory()).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.worker = None
        self.cancel_event = threading.Event()
        self.result = self.observations = self.chart = self.route = None
        self.obstacle_cancel = threading.Event()
        self.obstacle_workers = set()
        self.obstacle_generation = 0
        self.obstacle_revision = 0
        self.obstacle_report = {"state": "idle", "events": [], "mode": "foot", "reverse": False}
        self.current = self.pending = None
        self.online, self.model = online, model
        self.revision = 0
        self.state = {"phase": "idle", "message": "Prêt", "completed": 0, "total": 0, "filename": ""}
        self.cache_bytes = {"profiles": 0, "tiles": 0}
        self.cache_error = None
        self.tray = None
        self.restart_requested = False
        self.refresh_cache()
        self.version_checker = maj.Verificateur(updates.REPOSITORY, __version__, cache=self.directory / "maj.json")
        # Arguments of the new version after an update; serve() adds the port.
        self.relaunch = ["--data-dir", str(self.directory), "--no-browser"]
        self.installer = updates.installer(self.version_checker, self.stop, lambda: self.relaunch)

    def busy(self):
        return self.worker is not None

    def updating(self):
        """The new version is ready: gpx2elev is about to exit for the swap."""
        return self.installer.etat()["etat"] == "redemarrage"

    def load_language(self):
        settings = atomique.lire_json(self.directory / "settings.json", {})
        return settings.get("language") if isinstance(settings, dict) else None

    def save_language(self, code):
        path = self.directory / "settings.json"
        with self.lock, atomique.verrou_inter_processus(path):
            settings = atomique.lire_json(path, {})
            if not isinstance(settings, dict):
                settings = {}
            settings["language"] = code
            atomique.ecrire_json(path, settings)

    def init(self):
        return {"app": "gpx2elev", "version": __version__, "pid": os.getpid(),
                "data_dir": str(self.directory), "max_gpx_bytes": MAX_GPX_BYTES,
                "models": [{"id": s.name, "label": s.label} for s in RANKING], "translations": {**CATALOG, **WEB_TRANSLATIONS},
                "language": self.load_language(), "online": self.online, "model": self.model}

    def snapshot(self):
        with self.lock:
            return {**self.state, "busy": self.busy(), "revision": self.revision,
                    "has_result": self.result is not None, "has_input": self.current is not None,
                    "online": self.online, "model": self.model, "cache": self.cache_bytes.copy(),
                    "cache_error": self.cache_error, "obstacles": self.obstacle_report,
                    "obstacle_revision": self.obstacle_revision}

    def progress(self, message, completed=0, total=0):
        with self.lock:
            self.state.update(message=message, completed=completed, total=total)

    def refresh_cache(self):
        try:
            self.cache_bytes = cache_sizes(self.directory)
            self.cache_error = None
        except OSError:
            self.cache_error = "Taille du cache indisponible."

    def _options(self, payload):
        online = payload.get("online", self.online)
        model = payload.get("model", self.model)
        if type(online) is not bool or model not in (None, *Source.__members__):
            raise ValueError("Options de calcul invalides.")
        return online, model

    def _launch(self, name, data, online, model):
        if len(data) > MAX_GPX_BYTES:
            raise ValueError("Le GPX dépasse 20 Mo.")
        with self.lock:
            if self.busy() or self.updating():
                return {"error": "Une opération est déjà en cours."}
            self.current = (name, data)
            self.online, self.model = online, model
            self.result = self.observations = self.chart = self.route = None
            self.obstacle_cancel.set()
            self.obstacle_generation += 1
            self.obstacle_report = {"state": "idle", "events": [], "mode": self.obstacle_report["mode"],
                                    "reverse": self.obstacle_report["reverse"]}
            self.obstacle_revision += 1
            self.revision += 1
            self.cancel_event = threading.Event()
            self.state = {"phase": "calculate", "message": "Lecture de la trace GPX", "completed": 0,
                          "total": 0, "filename": name}
            self.worker = threading.Thread(target=self._calculate, args=(name, data, online, model), daemon=True)
            self.worker.start()
            return {"ok": True}

    def upload(self, payload):
        if not isinstance(payload, dict):
            return {"error": "Fichier GPX invalide."}
        try:
            name = _name(payload.get("name"))
            content = payload.get("content")
            if not isinstance(content, str) or len(content) > ((MAX_GPX_BYTES + 2) // 3) * 4:
                raise ValueError("Le GPX dépasse 20 Mo.")
            data = base64.b64decode(content, validate=True)
            online, model = self._options(payload)
            return self._launch(name, data, online, model)
        except (ValueError, TypeError) as exc:
            return {"error": str(exc)}

    def open_path(self, path, online=None, model=None, queue=False):
        path = Path(path).expanduser().resolve()
        name = _name(path.name)
        with path.open("rb") as stream:
            data = stream.read(MAX_GPX_BYTES + 1)
        if len(data) > MAX_GPX_BYTES:
            raise ValueError("Le GPX dépasse 20 Mo.")
        if path == self.directory / "last.gpx":
            metadata = atomique.lire_json(self.directory / "last.json", {})
            if isinstance(metadata, dict) and isinstance(metadata.get("name"), str):
                name = _name(metadata["name"])
        options = (name, data, self.online if online is None else online, self.model if model is None else model)
        with self.lock:
            if queue and self.busy():
                self.pending = options
                self.cancel_event.set()
                return {"ok": True, "queued": True}
            return self._launch(*options)

    def open_request(self, payload):
        if not isinstance(payload, dict) or not isinstance(payload.get("path"), str):
            return {"error": "Fichier GPX invalide."}
        try:
            online, model = self._options(payload)
            return self.open_path(payload["path"], online, model, queue=True)
        except (OSError, ValueError) as exc:
            self.report_open_error(exc)
            return {"error": str(exc)}

    def report_open_error(self, error):
        """Un GPX ouvert par le système ou la ligne de commande, mais illisible :
        l'erreur s'affiche dans la page au lieu d'arrêter l'application."""
        reason = error.strerror if isinstance(error, OSError) and error.strerror else str(error)
        with self.lock:
            if not self.busy():
                self.state.update(phase="error", message=f"Ouverture du GPX impossible : {reason}")

    def recalculate(self, payload):
        if not isinstance(payload, dict):
            return {"error": "Options de calcul invalides."}
        try:
            with self.lock:
                if self.current is None:
                    return {"error": "Choisissez d'abord un GPX."}
                return self._launch(*self.current, *self._options(payload))
        except ValueError as exc:
            return {"error": str(exc)}

    def _calculate(self, name, data, online, model):
        completed_result = None
        try:
            with tempfile.TemporaryDirectory(prefix="input-", dir=self.directory) as folder:
                path = Path(folder) / "input.gpx"
                path.write_bytes(data)
                result = calculate(path, self.directory, online, Source[model] if model else None,
                                   self.progress, self.cancel_event)
            if self.cancel_event.is_set():
                raise Cancelled()
            result.filename = name
            observations = ChartObservations(result.prepared, result.computed.profiles)
            chart = {"terrain": [{"x": _numbers(p.distance), "y": _numbers(p.elevations)} for p in result.computed.profiles],
                     "native": {"x": _numbers(observations.distance), "y": _numbers(observations.elevation),
                                "time": _numbers(observations.times), "group": observations.groups.tolist()}}
            with self.lock:
                self.result, self.observations, self.chart = result, observations, chart
                self.route = obstacles.route_view(result.prepared)
                completed_result = result
                self.state.update(phase="done", message="Calcul terminé", completed=0, total=0)
                self.revision += 1
            try:
                atomic_write(self.directory / "last.gpx", data)
                atomique.ecrire_json(self.directory / "last.json", {"name": name})
            except OSError:
                self.progress("Calcul terminé · sauvegarde de la dernière trace impossible.")
        except Cancelled:
            with self.lock:
                self.state.update(phase="cancelled", message="Calcul annulé.")
        except Exception as exc:
            with self.lock:
                self.state.update(phase="error", message=str(exc))
        finally:
            self._finished()
            with self.lock:
                if completed_result is not None and self.result is completed_result and not self.busy() and not self.stop_event.is_set():
                    self.check_obstacles({"online": online})

    def _finished(self):
        with self.lock:
            self.refresh_cache()
            self.worker = None
            pending, self.pending = self.pending, None
            if pending is not None and not self.stop_event.is_set():
                self._launch(*pending)

    def cancel(self, _payload=None):
        with self.lock:
            self.cancel_event.set()
            self.obstacle_cancel.set()
            if self.state["phase"] == "calculate":
                self.state["message"] = "Annulation en cours…"
        return {"ok": True}

    def get_result(self):
        with self.lock:
            return {"revision": self.revision, "summary": self.result.summary() if self.result else None,
                    "chart": self.chart, "route": self.route}

    def get_obstacles(self):
        with self.lock:
            return {**self.obstacle_report, "revision": self.obstacle_revision}

    def check_obstacles(self, payload):
        if not isinstance(payload, dict):
            return {"error": "Options des obstacles invalides."}
        with self.lock:
            if self.stop_event.is_set() or self.result is None or self.busy() or self.updating():
                return {"error": "Attendez le calcul du GPX avant de vérifier les obstacles."}
            mode = payload.get("mode", self.obstacle_report["mode"])
            reverse = payload.get("reverse", self.obstacle_report["reverse"])
            online = payload.get("online", self.online)
            refresh = payload.get("refresh", False)
            if mode not in obstacles.MODES or any(type(v) is not bool for v in (reverse, online, refresh)):
                return {"error": "Options des obstacles invalides."}
            self.obstacle_cancel.set()
            cancel = self.obstacle_cancel = threading.Event()
            self.obstacle_generation += 1
            generation = self.obstacle_generation
            prepared = self.result.prepared
            self.obstacle_report = {"state": "loading", "message": "Vérification des obstacles OSM…",
                                    "events": [], "mode": mode, "reverse": reverse}
            self.obstacle_revision += 1
            worker = threading.Thread(target=self._obstacles, args=(prepared, generation, cancel, online, mode, reverse, refresh), daemon=True)
            self.obstacle_workers.add(worker)
            worker.start()
            return {"ok": True}

    def _obstacles(self, prepared, generation, cancel, online, mode, reverse, refresh):
        try:
            report = obstacles.obtain(prepared, self.directory, online, mode, reverse, cancel, refresh)
        except Cancelled:
            report = {"state": "unavailable", "message": "Vérification annulée : obstacles non vérifiés.",
                      "events": [], "mode": mode, "reverse": reverse}
        except Exception:
            # A network/data failure must not be reported as zero barriers.
            report = {"state": "error", "message": "Service OSM indisponible ou réponse incomplète : obstacles non vérifiés. Réessayez.",
                      "events": [], "mode": mode, "reverse": reverse}
        finally:
            with self.lock:
                self.obstacle_workers.discard(threading.current_thread())
        with self.lock:
            if generation == self.obstacle_generation:
                self.obstacle_report = report
                self.obstacle_revision += 1
                self.refresh_cache()

    def select(self, x, y, left, right):
        try:
            x, y, left, right = (float(value) for value in (x, y, left, right))
        except (ValueError, TypeError):
            return {"error": "Position du curseur invalide."}
        if not all(math.isfinite(value) for value in (x, y, left, right)) or left > right:
            return {"error": "Position du curseur invalide."}
        with self.lock:
            if self.observations is None:
                return {"error": "Aucun profil disponible."}
            return asdict(self.observations.select(x, y, (left, right)))

    def export(self, kind):
        function = {"summary": export_summary, "profile": export_profile, "json": export_json}.get(kind)
        with self.lock:
            result = self.result
        if function is None or result is None:
            return {"error": "Aucun résultat à exporter."}
        extension = "json" if kind == "json" else "csv"
        suffix = {"summary": "resultats", "profile": "profil", "json": "resultats"}[kind]
        with tempfile.TemporaryDirectory(prefix="export-", dir=self.directory) as folder:
            path = Path(folder) / f"export.{extension}"
            function(result, path)
            return {"name": f"{Path(result.filename).stem}_{suffix}.{extension}", "content": path.read_bytes().decode("utf-8")}

    def clear(self, payload):
        if not isinstance(payload, dict) or payload.get("confirm") is not True:
            return {"error": "Confirmation requise."}
        with self.lock:
            if self.busy() or self.obstacle_workers or self.updating():
                return {"error": "Une opération est déjà en cours."}
            self.state.update(phase="cache", message="Suppression du cache…", completed=0, total=0)
            self.worker = threading.Thread(target=self._clear, daemon=True)
            self.worker.start()
            return {"ok": True}

    def _clear(self):
        try:
            clear_cache(self.directory)
            self.progress("Cache vidé.")
            with self.lock:
                self.state["phase"] = "done" if self.result else "idle"
        except OSError:
            with self.lock:
                self.state.update(phase="error", message="Impossible de vider complètement le cache.")
        finally:
            self._finished()

    def stop(self, _payload=None):
        self.stop_event.set()
        self.cancel_event.set()
        self.obstacle_cancel.set()
        if self.tray:
            self.tray.arret.set()
        return {"ok": True}

    def close(self):
        self.stop()
        # Registration and start happen under this lock: never join a thread
        # while another caller has registered it but has not started it yet.
        with self.lock:
            calculation = self.worker
            obstacle_workers = list(self.obstacle_workers)
        if calculation:
            calculation.join(40)
        for worker in obstacle_workers:
            worker.join(45)

    def routes(self):
        language_get, language_post = langue.routes(self.load_language, self.save_language, enregistrer_detection=True)
        # /api/maj, /api/maj-installer and /api/maj-verifier: the common update
        # banner (nico579-maj.js) and settings panel (nico579-reglages.js).
        update_get, update_post = maj_install.routes(self.installer, lambda: self.load_language() or "fr")
        return ({"init": self.init, "state": self.snapshot, "result": self.get_result, "select": self.select,
                 "obstacles": self.get_obstacles,
                 "export": self.export, **language_get, **update_get},
                {"upload": self.upload, "open": self.open_request, "recalculate": self.recalculate,
                 "obstacles": self.check_obstacles,
                 "cancel": self.cancel, "clear-cache": self.clear, "quit": self.stop, **language_post, **update_post})


class Handler(serveweb.Handler):
    fichiers_statiques = {**serveweb.FICHIERS_STATIQUES,
                          "/NotoSans.ttf": ("../NotoSans.ttf", "font/ttf"),
                          "/chart.js": ("chart.js", "text/javascript; charset=utf-8"),
                          "/route.js": ("route.js", "text/javascript; charset=utf-8")}
    arguments_get = {"export": lambda q: ((q.get("kind") or [""])[0],),
                     "select": lambda q: tuple((q.get(key) or ["0"])[0] for key in ("x", "y", "left", "right"))}

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length > ((MAX_GPX_BYTES + 2) // 3) * 4 + 65536:
            self.close_connection = True
            self.send_json({"error": "Le GPX dépasse 20 Mo."}, 413)
            return
        super().do_POST()


def start_server(application, port=0, port_range=1):
    get, post = application.routes()
    handler = type("GpxHandler", (Handler,), {})  # Each server keeps its own routes and state.
    server, _ = serveweb.premier_port_libre(HOST, port, port_range, trusted_host="", gui_dir=GUI,
        api_routes=get, post_routes=post, favicon=ASSETS / "gpx2elev.ico", handler=handler)
    if server is None:
        raise OSError("Aucun port disponible pour l'interface web.")
    return server, server.server_port


def _request(port, route, payload=None):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(f"http://{HOST}:{port}/api/{route}",
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={"Content-Type": "application/json"})
    with opener.open(request, timeout=2) as response:
        return json.load(response)



def _tidy_legacy_updates(stop_event, delay=15):
    """Remove what the updates of versions 0.3 and 0.4 left next to this
    installation, once their helper, which started this process, has exited."""
    if stop_event.wait(delay):
        return
    try:
        updates.remove_legacy_updates(updates.disposition().install_root)
    except (maj_archive.ErreurMiseAJour, OSError):
        pass  # From sources or outside the published bundle: nothing of ours.


def tray_actions(app, url, command):
    from nico579_commons import raccourci, tray
    import webbrowser

    def restart():
        app.restart_requested = True
        app.stop()

    def update():
        # The published bundle installs the new version by itself; otherwise
        # (sources, a folder that is not the bundle) the release page opens.
        if app.installer.possible()[0]:
            app.installer.demarrer()
            return
        info = app.version_checker.disponible()
        webbrowser.open(info["page"] if info else app.version_checker.page_des_releases)

    return tray.Actions(ouvrir=lambda: webbrowser.open(url), redemarrer=restart, arreter=app.stop,
        version_disponible=lambda: (app.version_checker.disponible() or {}).get("version"), mettre_a_jour=update,
        creer_raccourci=lambda: raccourci.creer("gpx2elev", command, Path(sys.executable).parent,
                                               icone=ASSETS / "gpx2elev.ico", langue=app.load_language() or "fr"),
        langue=lambda: app.load_language() or "fr", mettre_a_jour_referme=False)

def serve(args):
    from nico579_commons import relance, tray
    import webbrowser

    environnement.retablir_environnement_systeme()
    directory = Path(args.data_dir or data_directory()).resolve()
    if args.port and not args.new_instance:
        for port in range(args.port, min(65536, args.port + PORT_RANGE)):
            if not serveweb.instance_existante("gpx2elev", HOST, port, timeout=.15):
                continue
            try:
                if _request(port, "init").get("data_dir") != str(directory):
                    continue
            except (OSError, ValueError):
                continue
            status = 0
            if args.gpx:
                result = _request(port, "open", {"path": str(Path(args.gpx).resolve()),
                                                "online": not args.offline, "model": args.model})
                # L'instance ouverte affiche elle-même l'erreur : on la montre.
                status = 1 if result.get("error") else 0
            if not args.no_browser:
                webbrowser.open(f"http://{HOST}:{port}/")
            return status

    app = Application(directory, not args.offline, args.model)
    server = None
    try:
        server, port = start_server(app, args.port, min(PORT_RANGE, 65536 - args.port) if args.port else 1)
        url = f"http://{HOST}:{port}/"
        if sys.stdout:
            print(f"gpx2elev : {url}", flush=True)
        try:
            if args.gpx:
                app.open_path(args.gpx)
            elif (directory / "last.gpx").is_file():
                app.open_path(directory / "last.gpx", online=False)
        except (OSError, ValueError) as exc:
            # Sans console, une erreur ici arrêterait l'application sans rien montrer.
            app.report_open_error(exc)
        if args.update_result:
            # Versions 0.3 and 0.4 restart the version they installed with this argument.
            result = atomique.lire_json(args.update_result, {})
            if isinstance(result, dict) and result.get("status") == "ERROR":
                app.state.update(phase="error", message="La mise à jour a échoué. L\'ancienne version a été restaurée.")
        if not args.no_browser:
            webbrowser.open(url)
        arguments = ["--data-dir", str(directory), "--port", str(port)]
        if args.no_browser:
            arguments.append("--no-browser")
        if args.no_tray:
            arguments.append("--no-tray")
        command = ([sys.executable] if getattr(sys, "frozen", False) else
                   [sys.executable, str(Path(__file__).resolve().parents[1] / "launcher.py")]) + arguments
        # After an update the open page reloads itself (nico579-maj.js): no second tab.
        app.relaunch = arguments if args.no_browser else [*arguments, "--no-browser"]
        threading.Thread(target=_tidy_legacy_updates, args=(app.stop_event,), daemon=True).start()
        # Leftovers of an interrupted update next to the installation (helper killed,
        # power cut): removed in the background, startup is not delayed (nico579-commons 0.5).
        threading.Thread(target=app.installer.nettoyer_restes, name="menage-maj", daemon=True).start()

        if not args.offline:
            app.version_checker.veiller(app.stop_event)
        actions = tray_actions(app, url, command)
        if not args.no_tray and tray.disponible():
            app.tray = tray.Tray("gpx2elev", ASSETS / "gpx2elev.ico", actions)
            try:
                app.tray.executer()
            except Exception:
                app.tray = None
                app.stop_event.wait()
        else:
            app.stop_event.wait()
    except KeyboardInterrupt:
        app.stop()
    finally:
        app.close()
        if server:
            server.shutdown()
            server.server_close()
        if app.restart_requested:
            relance.relancer(command, nom="gpx2elev")
    return 0
