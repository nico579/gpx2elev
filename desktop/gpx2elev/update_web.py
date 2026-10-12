"""Manual update jobs for the browser UI, using the existing verified installer."""
from dataclasses import asdict
from pathlib import Path
import shutil
import tempfile
import threading

import requests

from .updates import (UpdateCancelled, UpdateClient, UpdateError, discard_install,
                      extract_bundle, installed_bundle, launch_helper, prepare_install)


class UpdateManager:
    def __init__(self, directory, stop, busy):
        self.directory = Path(directory)
        self.stop, self.busy = stop, busy
        self.lock = threading.RLock()
        self.worker = None
        self.cancel_event = threading.Event()
        self.release = self.prepared = self.pending_update = None
        self.advertised = lambda: None
        self.state = {"phase": "idle", "message": "", "completed": 0, "total": 0}

    def snapshot(self):
        with self.lock:
            advertised = self.advertised()
            return {**self.state, "advertised_version": advertised["version"] if advertised else None, "busy": self.worker is not None,
                    "release": asdict(self.release) if self.release else None,
                    "prepared": ("install" if "plan" in self.prepared else "folder") if self.prepared else None,
                    "can_install": installed_bundle() is not None}

    def progress(self, message, completed=0, total=0):
        with self.lock:
            self.state.update(message=message, completed=completed, total=total)

    def _start(self, operation):
        with self.lock:
            if self.worker is not None or self.pending_update is not None:
                return {"error": "Une opération est déjà en cours."}
            if operation == "download" and (self.release is None or self.prepared is not None):
                return {"error": "Aucune mise à jour à télécharger."}
            self.cancel_event = threading.Event()
            self.state = {"phase": operation, "message": "Recherche de mises à jour…" if operation == "check"
                          else "Téléchargement de la mise à jour…", "completed": 0, "total": 0}
            self.worker = threading.Thread(target=self._run, args=(operation,), daemon=True)
            self.worker.start()
            return {"ok": True}

    def check(self, _payload=None):
        return self._start("check")

    def download(self, _payload=None):
        return self._start("download")

    def _run(self, operation):
        client = UpdateClient(self.cancel_event)
        download_dir = None
        try:
            if operation == "check":
                if self.prepared and "plan" in self.prepared:
                    discard_install(self.prepared["plan"])
                with self.lock:
                    self.prepared = self.release = None
                release = client.check()
                with self.lock:
                    self.release = release
                    self.state.update(phase="available" if release else "latest",
                                      message="Une nouvelle version est disponible." if release
                                      else "Vous utilisez la dernière version publiée.")
            else:
                updates = self.directory / "updates"
                updates.mkdir(parents=True, exist_ok=True)
                download_dir = Path(tempfile.mkdtemp(prefix="download-", dir=updates))
                archive = client.download(self.release, download_dir,
                    lambda done, total: self.progress("Téléchargement de la mise à jour…", done, total))
                self.progress("Préparation de l'installation…")
                target = installed_bundle()
                if target is None:
                    prepared = {"folder": extract_bundle(archive, download_dir / "application", cancel=self.cancel_event)}
                    archive.unlink()
                    download_dir = None  # Keep the verified download for manual installation.
                else:
                    prepared = {"plan": prepare_install(archive, target, self.directory, self.cancel_event, self.release.version)}
                with self.lock:
                    self.prepared = prepared
                    self.state.update(phase="ready", message="Mise à jour vérifiée. Vous pouvez lancer l'installation."
                                      if target else "Mise à jour téléchargée. Ouvrez le dossier pour lancer la nouvelle version.")
        except UpdateCancelled:
            with self.lock:
                self.state.update(phase="cancelled", message="Annulation terminée.")
        except Exception as exc:
            message = (str(exc) if isinstance(exc, UpdateError) else
                       "Connexion au serveur de mises à jour impossible. Vérifiez Internet et réessayez."
                       if isinstance(exc, requests.RequestException) else
                       "Impossible d'écrire la mise à jour. Vérifiez l'espace libre et les droits du dossier."
                       if isinstance(exc, OSError) else "Archive de mise à jour invalide.")
            with self.lock:
                self.state.update(phase="error", message=message)
        finally:
            client.close()
            if download_dir is not None:
                shutil.rmtree(download_dir, ignore_errors=True)
            with self.lock:
                self.worker = None

    def cancel(self, _payload=None):
        with self.lock:
            self.cancel_event.set()
            return {"ok": True}

    def install(self, payload):
        with self.lock:
            if not isinstance(payload, dict) or payload.get("confirm") is not True:
                return {"error": "Confirmation requise."}
            if self.busy():
                return {"error": "Attendez la fin du calcul avant d'installer la mise à jour."}
            if self.worker is not None or not self.prepared or "plan" not in self.prepared or self.pending_update:
                return {"error": "Aucune mise à jour prête à installer."}
            try:
                launch_helper(self.prepared["plan"])
            except (OSError, UpdateError):
                return {"error": "Impossible de lancer l'installation de la mise à jour."}
            self.pending_update = self.prepared["plan"]
            self.state.update(phase="installing", message="Mise à jour vérifiée. L'application va se fermer puis redémarrer.")
            self.stop()
            return {"ok": True}

    def open_folder(self, _payload=None):
        with self.lock:
            if not self.prepared or "folder" not in self.prepared:
                return {"error": "Aucun dossier disponible."}
            folder = self.prepared["folder"].parent
        import webbrowser
        webbrowser.open(folder.as_uri())
        return {"ok": True}

    def close(self):
        self.cancel_event.set()
        worker = self.worker
        if worker is not None:
            worker.join(40)
        if self.prepared and "plan" in self.prepared and self.pending_update is None and self.worker is None:
            discard_install(self.prepared["plan"])
