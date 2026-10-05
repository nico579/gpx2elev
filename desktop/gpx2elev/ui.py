"""Native Qt desktop window. Long calculations never run on the UI thread."""
import json
from pathlib import Path
import threading

import numpy as np
from PySide6.QtCore import QEvent, QLocale, QPointF, QRectF, QStandardPaths, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QProgressBar,
    QPushButton, QSizePolicy, QTextBrowser, QVBoxLayout, QWidget)

from . import __version__
from .i18n import translate, number
from .providers import Cancelled, RANKING, atomic_write
from .service import calculate, export_profile, export_summary
from .cache import cache_sizes, clear_cache


class CacheWorker(QThread):
    failed = Signal(str)

    def __init__(self, directory, parent=None):
        super().__init__(parent)
        self.directory = directory

    def run(self):
        try:
            clear_cache(self.directory)
        except OSError:
            self.failed.emit("Impossible de vider complètement le cache.")


def data_directory():
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))


class LanguageLabel(QLabel):
    def __init__(self, text="", *args, **kwargs):
        super().__init__(text, *args, **kwargs)
        self.original = text

    def setText(self, text):
        self.original = text
        self.retranslate()

    def retranslate(self):
        window = self.window()
        super().setText(window.tr(self.original) if isinstance(window, MainWindow)
                        and self.property("literal") is not True else self.original)

    def setLiteralText(self, text):
        self.setProperty("literal", True)
        self.setText(text)


class LanguageBrowser(QTextBrowser):
    original = ""

    def setPlainText(self, text):
        self.original = text
        self.retranslate()

    def retranslate(self):
        window = self.window()
        super().setPlainText(window.tr(self.original) if isinstance(window, MainWindow) else self.original)


def app_icon():
    from PySide6.QtGui import QPixmap
    image = QPixmap(128, 128)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#176c59"))
    painter.drawRoundedRect(QRectF(0, 0, 128, 128), 28, 28)
    painter.setPen(QPen(QColor("white"), 9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    path = QPainterPath(QPointF(22, 91))
    for x, y in ((49, 44), (64, 65), (83, 33), (108, 91)):
        path.lineTo(x, y)
    painter.drawPath(path)
    painter.end()
    return QIcon(image)


class ProfileChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.result = None
        self.setMinimumHeight(140)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName("Profil d'altitude lissé, distance en kilomètres et altitude en mètres")

    def number(self, value, decimals=0):
        return number(value, decimals, self.window().language)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("white"))
        if self.result is None:
            painter.setPen(QColor("#6b7c88"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.window().tr("Le profil d’altitude apparaîtra ici"))
            return
        profiles = self.result.computed.profiles
        length = max(self.result.prepared.length, 1)
        bottom, top = self.result.computed.minimum, self.result.computed.maximum
        margin = max((top - bottom) * .12, 5)
        low, high = bottom - margin, top + margin
        chart = QRectF(65, 15, max(1, self.width() - 88), max(1, self.height() - 55))
        font = QFont(self.font())
        font.setPointSize(9)
        painter.setFont(font)
        for i in range(5):
            y = chart.top() + chart.height() * i / 4
            painter.setPen(QPen(QColor("#e4ece9"), 1))
            painter.drawLine(QPointF(chart.left(), y), QPointF(chart.right(), y))
            painter.setPen(QColor("#64756e"))
            painter.drawText(QRectF(0, y - 9, 56, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self.number(high - (high - low) * i / 4) + " m")
        for i in range(5):
            x = chart.left() + chart.width() * i / 4
            painter.setPen(QColor("#64756e"))
            painter.drawText(QRectF(x - 32, chart.bottom() + 9, 64, 20), Qt.AlignmentFlag.AlignCenter, self.number(length * i / 4000, 1) + " km")
        for profile in profiles:
            # Bound drawing work while retaining each bucket's minimum and maximum.
            n = len(profile.distance)
            if n <= 3000:
                indices = np.arange(n)
            else:
                buckets = np.linspace(0, n, 1000, dtype=int)
                selected = [0, n - 1]
                for a, b in zip(buckets[:-1], buckets[1:]):
                    z = profile.elevations[a:b]
                    selected.extend((a + int(z.argmin()), a + int(z.argmax())))
                indices = np.unique(selected)
            path = QPainterPath()
            for k, i in enumerate(indices):
                x = chart.left() + float(profile.distance[i]) / length * chart.width()
                y = chart.bottom() - (float(profile.elevations[i]) - low) / (high - low) * chart.height()
                if k == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            area = QPainterPath(path)
            area.lineTo(chart.left() + float(profile.distance[-1]) / length * chart.width(), chart.bottom())
            area.lineTo(chart.left() + float(profile.distance[0]) / length * chart.width(), chart.bottom())
            area.closeSubpath()
            painter.fillPath(area, QColor("#e1f1e9"))
            painter.setPen(QPen(QColor("#176c59"), 2.4))
            painter.drawPath(path)
        painter.end()


class Worker(QThread):
    progress = Signal(str, int, int)
    ready = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, path, directory, online, source, parent=None):
        super().__init__(parent)
        self.path, self.directory, self.online, self.source = path, directory, online, source
        self.cancel_event = threading.Event()

    def run(self):
        try:
            result = calculate(self.path, self.directory, self.online, self.source, self.progress.emit, self.cancel_event)
            self.ready.emit(result)
        except Cancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


STYLE = """
QMainWindow, QWidget#main { background: #f4f7f5; color: #203c33; }
QLabel { color: #203c33; }
QLabel#subtitle { color: #62776d; }
QFrame#card { background: white; border: 1px solid #dce8e1; border-radius: 13px; }
QPushButton { padding: 10px 17px; border: 1px solid #cbded3; border-radius: 8px; background: white; color: #245244; }
QPushButton:hover { background: #eaf3ee; }
QPushButton#primary { background: #176c59; color: white; border: 1px solid #176c59; font-weight: 600; }
QPushButton#primary:hover { background: #125542; }
QPushButton:disabled { color: #82918a; background: #e5ebe7; }
QComboBox { background: white; color: #203c33; border: 1px solid #cbded3; border-radius: 7px; padding: 7px 10px; min-width: 155px; }
QComboBox QAbstractItemView { background: white; color: #203c33; selection-background-color: #d2e9dc; }
QCheckBox { color: #365e4d; spacing: 6px; }
QProgressBar { border: none; border-radius: 4px; background: #dfe9e2; height: 7px; text-align: center; color: #203c33; }
QProgressBar::chunk { background: #228164; border-radius: 4px; }
QTextBrowser { color: #365e4d; background: white; border: 1px solid #dce8e1; border-radius: 8px; padding: 8px; }
"""


class MainWindow(QMainWindow):
    def __init__(self, directory=None, restore=True):
        super().__init__()
        self.directory = Path(directory) if directory is not None else data_directory()
        try:
            self.language = json.loads((self.directory / "settings.json").read_text(encoding="utf-8")).get("language")
        except (OSError, ValueError):
            self.language = None
        if self.language not in ("fr", "en"):
            self.language = "fr" if QLocale.system().language() == QLocale.Language.French else "en"
        self.result = None
        self.worker = None
        self.cache_worker = None
        self.cache_error = None
        self.cache_bytes = {"profiles": 0, "tiles": 0}
        self.closing = False
        self.pending_path = None
        self.current_path = None
        self.setWindowTitle(f"gpx2elev · {__version__}")
        self.setWindowIcon(app_icon())
        self.resize(1000, 820)
        self.setMinimumSize(780, 700)
        self.setAcceptDrops(True)
        self.setStyleSheet(STYLE)
        main = QWidget(objectName="main")
        self.setCentralWidget(main)
        layout = QVBoxLayout(main)
        layout.setContentsMargins(28, 22, 28, 20)
        layout.setSpacing(12)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = LanguageLabel("gpx2elev")
        title.setFont(QFont(self.font().family(), 26, QFont.Weight.Bold))
        title_box.addWidget(title)
        title_box.addWidget(LanguageLabel("Le dénivelé de votre parcours, à partir du terrain", objectName="subtitle"))
        header.addLayout(title_box)
        header.addStretch()
        about = QPushButton("Méthode et sources")
        about.clicked.connect(self.about)
        header.addWidget(about)
        self.language_picker = QComboBox()
        self.language_picker.addItem("FR", "fr")
        self.language_picker.addItem("EN", "en")
        self.language_picker.setStyleSheet("QComboBox { min-width: 48px; }")
        self.language_picker.setCurrentIndex(0 if self.language == "fr" else 1)
        self.language_picker.setAccessibleName("Language / Langue")
        self.language_picker.currentIndexChanged.connect(self.select_language)
        header.addWidget(self.language_picker)
        layout.addLayout(header)
        controls = QHBoxLayout()
        self.import_button = QPushButton("Choisir un GPX", objectName="primary")
        self.import_button.clicked.connect(self.choose)
        controls.addWidget(self.import_button)
        self.recalculate = QPushButton("Recalculer")
        self.recalculate.setEnabled(False)
        self.recalculate.clicked.connect(lambda: self.open_path(self.current_path))
        controls.addWidget(self.recalculate)
        controls.addStretch()
        self.models = QComboBox()
        self.models.addItem("Modèle automatique", None)
        for source in RANKING:
            self.models.addItem(source.label, source)
        self.models.setAccessibleName("Modèle d'altitude")
        controls.addWidget(self.models)
        self.online = QCheckBox("Internet autorisé")
        self.online.setChecked(True)
        controls.addWidget(self.online)
        layout.addLayout(controls)
        self.filename = LanguageLabel("Déposez un fichier GPX dans cette fenêtre, ou choisissez-le ci-dessus.")
        self.filename.setWordWrap(True)
        layout.addWidget(self.filename)
        self.source_label = LanguageLabel("Source : sélection automatique selon la couverture", objectName="subtitle")
        layout.addWidget(self.source_label)
        cards = QGridLayout()
        self.up = self.metric_card(cards, 0, "DÉNIVELÉ POSITIF ESTIMÉ", "— m", "Montée")
        self.down = self.metric_card(cards, 1, "DÉNIVELÉ NÉGATIF ESTIMÉ", "— m", "Descente")
        self.length = self.metric_card(cards, 2, "DISTANCE DU PARCOURS", "— km", "Sur les coordonnées GPX")
        layout.addLayout(cards)
        self.chart = ProfileChart()
        layout.addWidget(self.chart, 1)
        self.range_label = LanguageLabel("Profil lissé · pas 5 m · gaussienne σ = 20 m · hystérésis 2 m", objectName="subtitle")
        layout.addWidget(self.range_label)
        self.comparison = LanguageLabel("Altitudes GPX : les sommes brutes et filtrées seront affichées après le calcul.")
        self.comparison.setWordWrap(True)
        layout.addWidget(self.comparison)
        self.details = LanguageBrowser()
        self.details.setMaximumHeight(86)
        self.details.hide()
        layout.addWidget(self.details)
        bottom = QHBoxLayout()
        self.export_button = QPushButton("Exporter les résultats CSV")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.save_summary)
        bottom.addWidget(self.export_button)
        self.profile_button = QPushButton("Exporter le profil CSV")
        self.profile_button.setEnabled(False)
        self.profile_button.clicked.connect(self.save_profile)
        bottom.addWidget(self.profile_button)
        bottom.addStretch()
        self.cancel_button = QPushButton("Annuler")
        self.cancel_button.hide()
        self.cancel_button.clicked.connect(self.cancel)
        bottom.addWidget(self.cancel_button)
        layout.addLayout(bottom)
        cache_row = QHBoxLayout()
        self.cache_label = LanguageLabel(objectName="subtitle")
        self.cache_label.setWordWrap(True)
        cache_row.addWidget(self.cache_label, 1)
        self.clear_cache_button = QPushButton("Vider le cache")
        self.clear_cache_button.clicked.connect(self.confirm_clear_cache)
        cache_row.addWidget(self.clear_cache_button)
        layout.addLayout(cache_row)
        self.status = LanguageLabel("Prêt", objectName="subtitle")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)
        self.apply_language()
        self.refresh_cache()
        if restore:
            QTimer.singleShot(0, self.restore)

    def tr(self, text):
        return translate(text, self.language)

    def number(self, value, decimals=0):
        return number(value, decimals, self.language)

    def select_language(self):
        self.language = self.language_picker.currentData()
        self.apply_language()
        atomic_write(self.directory / "settings.json", json.dumps({"language": self.language}).encode())

    def apply_language(self):
        for widget in self.findChildren(LanguageLabel) + self.findChildren(LanguageBrowser):
            widget.retranslate()
        for widget in self.findChildren(QPushButton) + self.findChildren(QCheckBox):
            original = widget.property("original_text")
            if original is None:
                original = widget.text()
                widget.setProperty("original_text", original)
            widget.setText(self.tr(original))
        self.models.setItemText(0, self.tr("Modèle automatique"))
        self.models.setAccessibleName(self.tr("Modèle d'altitude"))
        self.chart.setAccessibleName(self.tr("Profil d'altitude lissé, distance en kilomètres et altitude en mètres"))
        if self.result is not None:
            self.show_result(self.result)
        self.chart.update()
        self.show_cache_size()

    def show_cache_size(self):
        def size(value):
            if value < 1024:
                return self.number(value) + " " + self.tr("octets")
            if value < 1048576:
                return self.number(value / 1024, 1) + " " + self.tr("Kio")
            return self.number(value / 1048576, 1) + " " + self.tr("Mio")
        self.cache_label.setLiteralText(self.tr("Cache des altitudes") + " : " + size(sum(self.cache_bytes.values())) +
            " · " + self.tr("Profils") + " " + size(self.cache_bytes['profiles']) + " / 64 " + self.tr("Mio") +
            " · " + self.tr("Tuiles") + " " + size(self.cache_bytes['tiles']) + " / 512 " + self.tr("Mio"))

    def refresh_cache(self):
        try:
            self.cache_bytes = cache_sizes(self.directory)
        except OSError:
            self.cache_label.setText("Taille du cache indisponible.")
            return
        self.show_cache_size()
        self.clear_cache_button.setEnabled(self.worker is None and self.cache_worker is None and sum(self.cache_bytes.values()) > 0)

    def confirm_clear_cache(self):
        if self.worker is not None or self.cache_worker is not None:
            return
        answer = QMessageBox.question(self, self.tr("Vider le cache ?"),
            self.tr("Les altitudes devront être téléchargées à nouveau. Le GPX, les réglages et le résultat affiché sont conservés."),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.start_clear_cache()

    def start_clear_cache(self):
        if self.worker is not None or self.cache_worker is not None:
            return
        for control in (self.clear_cache_button, self.import_button, self.recalculate, self.models, self.online):
            control.setEnabled(False)
        self.status.setText("Suppression du cache…")
        self.cache_error = None
        self.cache_worker = CacheWorker(self.directory, self)
        self.cache_worker.failed.connect(lambda message: setattr(self, 'cache_error', message))
        self.cache_worker.finished.connect(self.cache_cleared)
        self.cache_worker.start()

    def cache_cleared(self):
        worker, self.cache_worker = self.cache_worker, None
        worker.deleteLater()
        self.import_button.setEnabled(True)
        self.recalculate.setEnabled(self.current_path is not None)
        self.models.setEnabled(True)
        self.online.setEnabled(True)
        self.status.setText(self.cache_error or "Cache vidé.")
        self.refresh_cache()
        self.resume_pending()

    def metric_card(self, layout, column, title, initial, footer):
        frame = QFrame(objectName="card")
        box = QVBoxLayout(frame)
        box.setContentsMargins(18, 14, 18, 14)
        label = LanguageLabel(title, objectName="subtitle")
        label.setFont(QFont(self.font().family(), 9))
        box.addWidget(label)
        value = LanguageLabel(initial)
        value.setFont(QFont(self.font().family(), 28, QFont.Weight.Bold))
        box.addWidget(value)
        box.addWidget(LanguageLabel(footer, objectName="subtitle"))
        layout.addWidget(frame, 0, column)
        return value

    def choose(self):
        filename, _ = QFileDialog.getOpenFileName(self, self.tr("Choisir une trace"), "", self.tr("Traces GPX (*.gpx *.GPX);;Tous les fichiers (*)"))
        if filename:
            self.open_path(filename)

    def receive_path(self, path):
        """Native file-open events can arrive during startup or another calculation."""
        if self.closing:
            return
        if self.worker is not None or self.cache_worker is not None:
            self.pending_path = path
            self.cancel()
        else:
            self.open_path(path)

    def open_path(self, path, online_override=None):
        if not path or self.worker is not None or self.cache_worker is not None:
            return
        self.current_path = Path(path)
        self.filename.setLiteralText(self.current_path.name)
        self.result = None
        self.chart.result = None
        self.chart.update()
        for label, text in ((self.up, "— m"), (self.down, "— m"), (self.length, "— km")):
            label.setText(text)
        self.comparison.setText("Calcul en cours…")
        self.source_label.setText("Recherche du modèle d'altitude…")
        self.details.hide()
        self.export_button.setEnabled(False)
        self.profile_button.setEnabled(False)
        self.import_button.setEnabled(False)
        self.recalculate.setEnabled(False)
        self.models.setEnabled(False)
        self.online.setEnabled(False)
        self.clear_cache_button.setEnabled(False)
        self.progress_bar.show()
        self.cancel_button.show()
        self.cancel_button.setEnabled(True)
        online = self.online.isChecked() if online_override is None else online_override
        self.worker = Worker(self.current_path, self.directory, online, self.models.currentData(), self)
        self.worker.progress.connect(self.on_progress)
        self.worker.ready.connect(self.show_result)
        self.worker.failed.connect(self.show_error)
        self.worker.cancelled.connect(lambda: self.status.setText("Calcul annulé."))
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def on_progress(self, message, completed, total):
        self.status.setText(message)
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(completed)

    def show_result(self, result):
        if self.current_path == self.directory / "last.gpx":
            try:
                saved_name = json.loads((self.directory / "last.json").read_text(encoding="utf-8"))["name"]
                if isinstance(saved_name, str):
                    result.filename = Path(saved_name).name
            except (OSError, ValueError, KeyError):
                pass
        self.result = result
        self.filename.setLiteralText(result.filename)
        self.up.setText("+" + self.number(result.computed.gain.up) + " m")
        self.down.setText("−" + self.number(result.computed.gain.down) + " m")
        self.length.setText(self.number(result.prepared.length / 1000, 2) + " km")
        cache = " · profil en cache" if result.series.from_cache else ""
        self.source_label.setText("Source : " + result.series.source.label + cache)
        self.chart.result = result
        self.chart.update()
        self.range_label.setText(f"Altitude {self.number(result.computed.minimum)}–{self.number(result.computed.maximum)} m · pas 5 m · σ = 20 m · hystérésis 2 m")
        def gain_text(gain):
            return f"D+ {self.number(gain.up)} m / D− {self.number(gain.down)} m" if gain is not None else "altitudes absentes ou incomplètes"
        self.comparison.setText("Comparaison GPX\nSomme brute des variations : " + gain_text(result.computed.gpx_raw) + "\nGPX rééchantillonné et filtré : " + gain_text(result.computed.gpx_filtered))
        if result.series.fallbacks:
            self.details.setPlainText("Repli entre modèles :\n" + "\n".join(f"{s.label} : {r}" for s, r in result.series.fallbacks))
            self.details.show()
        self.export_button.setEnabled(True)
        self.profile_button.setEnabled(True)
        self.status.setText(f"Calcul terminé · {self.number(result.prepared.track.point_count)} points GPX · {self.number(result.prepared.sample_count)} positions à 5 m")
        # Preserve one validated input locally, so moving the original does not break restoration.
        if self.current_path is not None:
            try:
                atomic_write(self.directory / "last.gpx", self.current_path.read_bytes())
                atomic_write(self.directory / "last.json", json.dumps({"name": result.filename}, ensure_ascii=False).encode())
            except OSError:
                pass

    def show_error(self, message):
        self.status.setText("Calcul impossible. Consultez le détail ci-dessus.")
        self.source_label.setText("Aucun profil complet disponible")
        self.comparison.setText("Les altitudes n'ont pas pu être calculées.")
        self.details.setPlainText(message)
        self.details.show()

    def finished(self):
        worker = self.worker
        self.worker = None
        if worker is not None:
            worker.deleteLater()
        self.import_button.setEnabled(True)
        self.recalculate.setEnabled(self.current_path is not None)
        self.models.setEnabled(True)
        self.online.setEnabled(True)
        self.cancel_button.hide()
        self.progress_bar.hide()
        self.refresh_cache()
        self.resume_pending()

    def resume_pending(self):
        if self.closing:
            QTimer.singleShot(0, self.close)
        elif self.pending_path is not None:
            path, self.pending_path = self.pending_path, None
            QTimer.singleShot(0, lambda: self.open_path(path))

    def cancel(self):
        if self.worker is not None:
            self.worker.cancel_event.set()
            self.cancel_button.setEnabled(False)
            self.status.setText("Annulation en cours…")

    def restore(self):
        path = self.directory / "last.gpx"
        if self.current_path is None and path.exists():
            self.open_path(path, online_override=False)

    def save_summary(self):
        self.export(export_summary, "resultats")

    def save_profile(self):
        self.export(export_profile, "profil")

    def export(self, function, suffix):
        if self.result is None:
            return
        name = Path(self.result.filename).stem + "_" + suffix + ".csv"
        path, _ = QFileDialog.getSaveFileName(self, self.tr("Exporter en CSV"), name, self.tr("Fichiers CSV (*.csv)"))
        if path:
            try:
                function(self.result, path)
                self.status.setText("Export enregistré : " + Path(path).name)
            except OSError as exc:
                QMessageBox.warning(self, self.tr("Export impossible"), self.tr(str(exc)))

    def about(self):
        QMessageBox.about(self, self.tr("Méthode et sources"), self.tr("<h3>gpx2elev " + __version__ + "</h3>"
            "<p>D+ estimé : rééchantillonnage à 5 m, gaussienne spatiale σ = 20 m (rayon 80 m), hystérésis de 2 m. "
            "Les segments et leurs extrémités sont conservés. Les coordonnées XY ne sont pas corrigées.</p>"
            "<p>Ordre automatique : IGN LiDAR HD → Mapterhorn → FABDEM → Copernicus GLO-30 → SRTM90. "
            "Un seul modèle couvre toute la trace. Le GPX brut reste une comparaison distincte.</p>"
            "<p>Le premier calcul demande Internet. Les coordonnées sont envoyées à l'IGN ; les autres modèles sont lus dans des tuiles publiques. "
            "Les profils et la dernière trace sont conservés localement. Aucune télémétrie.</p>"
            "<p>IGN : Licence Ouverte. <a href='https://mapterhorn.com/attribution/'>Mapterhorn : producteurs</a>. "
            "<a href='https://research-information.bris.ac.uk/en/datasets/fabdem-v1-2/'>FABDEM 1.2 : CC BY-NC-SA 4.0</a>. "
            "<a href='https://registry.opendata.aws/copernicus-dem/'>Copernicus : licence DEM</a>. SRTM : NASA/USGS, miroir Kurviger.</p>"
            "<p>Interface Qt/PySide6 sous LGPLv3. Les licences des dépendances sont incluses dans le bundle.</p>"))

    def dragEnterEvent(self, event):
        if self.worker is None and self.cache_worker is None and event.mimeData().hasUrls() and any(u.isLocalFile() and Path(u.toLocalFile()).suffix.lower() == ".gpx" for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() == ".gpx":
                self.open_path(url.toLocalFile())
                event.acceptProposedAction()
                break

    def closeEvent(self, event):
        if self.worker is not None or self.cache_worker is not None:
            self.closing = True
            self.cancel()
            event.ignore()
        else:
            event.accept()


class DesktopApplication(QApplication):
    """Receive Finder's native file-open events on macOS, including launch events."""
    def __init__(self, argv):
        self.window = None
        self.pending_path = None
        super().__init__(argv)
        self.setApplicationName("gpx2elev")
        self.setOrganizationName("Nico")
        self.setApplicationVersion(__version__)
        self.setWindowIcon(app_icon())
        # Bundle an OFL font: identical glyph coverage, including headless Windows.
        font_path = Path(__file__).resolve().parent / "assets/NotoSans.ttf"
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
        if families:
            self.setFont(QFont(families[0], 10))

    def event(self, event):
        if event.type() == QEvent.Type.FileOpen:
            path = event.file()
            if path:
                if self.window is None:
                    self.pending_path = path
                else:
                    self.window.receive_path(path)
            return True
        return super().event(event)
