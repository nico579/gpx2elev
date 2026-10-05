"""gpx2elev desktop: the same spatial protocol as the Android application."""

from pathlib import Path

__version__ = (Path(__file__).parent / "assets/version.txt").read_text(encoding="utf-8").strip()
