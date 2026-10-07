"""Qt update dialog; network, extraction and helper preparation run off the UI thread."""
from pathlib import Path
import shutil
import tempfile
import threading

import requests
from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTextBrowser, QVBoxLayout

from . import __version__
from .updates import (UpdateCancelled, UpdateClient, UpdateError, extract_bundle,
                      discard_install, installed_bundle, launch_helper, prepare_install)


class UpdateWorker(QThread):
    ready = Signal(object)
    progress = Signal(str, int, int)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, directory, release=None, parent=None, cleanup_plan=None):
        super().__init__(parent)
        self.directory, self.release = Path(directory), release
        self.cancel_event = threading.Event()
        self.cleanup_plan = cleanup_plan

    def run(self):
        client = UpdateClient(self.cancel_event)
        download_dir = None
        try:
            if self.cleanup_plan is not None:
                discard_install(self.cleanup_plan)
                result = None
            elif self.release is None:
                result = client.check()
            else:
                updates = self.directory / "updates"
                updates.mkdir(parents=True, exist_ok=True)
                download_dir = Path(tempfile.mkdtemp(prefix="download-", dir=updates))
                archive = client.download(self.release, download_dir,
                    lambda done, total: self.progress.emit("Téléchargement de la mise à jour…", done, total))
                self.progress.emit("Préparation de l'installation…", 0, 0)
                target = installed_bundle()
                if target is None:
                    result = {"folder": extract_bundle(archive, download_dir / "application", cancel=self.cancel_event)}
                    archive.unlink()
                    download_dir = None  # Keep the verified bundle for manual installation in source mode.
                else:
                    result = {"plan": prepare_install(archive, target, self.directory, self.cancel_event, self.release.version)}
            self.ready.emit(result)
        except UpdateCancelled:
            self.cancelled.emit()
        except UpdateError as exc:
            self.failed.emit(str(exc))
        except requests.RequestException:
            self.failed.emit("Connexion au serveur de mises à jour impossible. Vérifiez Internet et réessayez.")
        except OSError:
            self.failed.emit("Impossible d'écrire la mise à jour. Vérifiez l'espace libre et les droits du dossier.")
        except Exception:
            self.failed.emit("Archive de mise à jour invalide.")
        finally:
            client.close()
            if download_dir is not None:
                shutil.rmtree(download_dir, ignore_errors=True)


class UpdateDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.owner = window
        self.worker = self.release = self.prepared = None
        self.closing = False
        self.status_text = "Recherche de mises à jour…"
        self.action_text = "Télécharger et installer"
        self.setModal(True)
        self.resize(560, 350)
        layout = QVBoxLayout(self)
        self.installed_label = QLabel()
        layout.addWidget(self.installed_label)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.notes = QTextBrowser()
        self.notes.setOpenExternalLinks(False)
        self.notes.hide()
        layout.addWidget(self.notes)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        layout.addWidget(self.progress_bar)
        buttons = QHBoxLayout()
        self.check_button = QPushButton()
        self.check_button.clicked.connect(self.check)
        buttons.addWidget(self.check_button)
        buttons.addStretch()
        self.action_button = QPushButton()
        self.action_button.setObjectName("primary")
        self.action_button.clicked.connect(self.perform_action)
        self.action_button.hide()
        buttons.addWidget(self.action_button)
        self.close_button = QPushButton()
        self.close_button.clicked.connect(self.reject)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)
        self.retranslate()

    def retranslate(self):
        t = self.owner.tr
        self.setWindowTitle(t("Mises à jour"))
        self.installed_label.setText(t("Version installée : {0}").format(__version__))
        self.status_label.setText(t(self.status_text))
        self.check_button.setText(t("Vérifier à nouveau"))
        self.action_button.setText(t(self.action_text))
        self.close_button.setText(t("Annuler" if self.worker is not None else "Fermer"))

    def check(self):
        if self.worker is not None or self.prepared is not None:
            return
        self.release = None
        self.status_text = "Recherche de mises à jour…"
        self.action_button.hide()
        self.notes.hide()
        self.start_worker()

    def start_worker(self, release=None, cleanup_plan=None):
        self.worker = UpdateWorker(self.owner.directory, release, self, cleanup_plan)
        self.worker.ready.connect(self.on_ready)
        self.worker.failed.connect(self.on_failed)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_finished)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.show()
        self.check_button.setEnabled(False)
        self.action_button.setEnabled(False)
        self.retranslate()
        self.worker.start()

    def on_progress(self, text, done, total):
        self.status_text = text
        self.progress_bar.setRange(0, 100 if total else 0)
        if total:
            self.progress_bar.setValue(round(done * 100 / total))
        self.retranslate()

    def on_ready(self, value):
        if self.closing:
            if isinstance(value, dict) and "plan" in value:
                self.prepared = value  # Cleanup waits for the preparation thread to finish.
            return
        if self.worker.release is None:
            self.release = value
            if value is None:
                self.status_text = "Vous utilisez la dernière version publiée."
                self.action_button.hide()
            else:
                self.status_text = "Version {0} disponible · {1:.1f} Mio".format(value.version, value.size / 1048576)
                self.notes.setPlainText(value.notes)
                self.notes.setVisible(bool(value.notes))
                self.action_text = "Télécharger et installer" if installed_bundle() else "Télécharger"
                self.action_button.show()
        else:
            self.prepared = value
            if "plan" in value:
                self.status_text = "Mise à jour vérifiée. L'application va se fermer puis redémarrer."
                self.action_text = "Installer et redémarrer"
            else:
                self.status_text = "Mise à jour téléchargée. Ouvrez le dossier pour lancer la nouvelle version."
                self.action_text = "Ouvrir le dossier"
            self.action_button.show()
        self.retranslate()

    def on_failed(self, message):
        self.status_text = message
        self.retranslate()

    def on_finished(self):
        worker, self.worker = self.worker, None
        worker.deleteLater()
        if self.closing and self.prepared is not None and "plan" in self.prepared and self.owner.pending_update is None:
            plan, self.prepared = self.prepared["plan"], None
            self.start_worker(cleanup_plan=plan)
            return
        self.progress_bar.hide()
        self.check_button.setEnabled(self.prepared is None)
        self.action_button.setEnabled(self.release is not None or self.prepared is not None)
        self.retranslate()
        if self.closing:
            super().reject()
            if self.owner.closing:
                self.owner.close()

    def perform_action(self):
        if self.worker is not None:
            return
        if self.prepared is None and self.release is not None:
            self.status_text = "Téléchargement de la mise à jour…"
            self.start_worker(self.release)
        elif self.prepared is not None and "folder" in self.prepared:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.prepared["folder"].parent)))
        elif self.prepared is not None:
            if self.owner.worker is not None or self.owner.cache_worker is not None:
                self.on_failed("Attendez la fin du calcul avant d'installer la mise à jour.")
                return
            try:
                launch_helper(self.prepared["plan"])
            except (OSError, UpdateError):
                self.on_failed("Impossible de lancer l'installation de la mise à jour.")
                return
            self.owner.pending_update = self.prepared["plan"]
            self.accept()
            self.owner.close()

    def reject(self):
        if self.worker is not None:
            self.closing = True
            self.worker.cancel_event.set()
            self.close_button.setEnabled(False)
            self.status_text = "Annulation en cours…"
            self.retranslate()
        elif self.prepared is not None and "plan" in self.prepared and self.owner.pending_update is None:
            plan, self.prepared = self.prepared["plan"], None
            self.closing = True
            self.start_worker(cleanup_plan=plan)
        else:
            super().reject()
