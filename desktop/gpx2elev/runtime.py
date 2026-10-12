"""Application paths and assets, also usable without a desktop session."""
from pathlib import Path

from nico579_commons.dossiers import Dossiers

# Keep the data directory used by the previous desktop application on all OSes.
DOSSIERS = Dossiers("gpx2elev", nom_etat="Nico/gpx2elev", preferences="settings.json")
ASSETS = Path(__file__).resolve().parent / "assets"
GUI = ASSETS / "web"


def data_directory():
    return DOSSIERS.dossier_etat()
