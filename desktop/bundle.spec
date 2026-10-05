# Native build only: run on each target operating system.
from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

root = Path(SPECPATH)
assets = root / "build/assets"
resources = root.parent / "app/src/test/resources"
datas = [(str(assets / "licenses"), "licenses"), (str(root / "README.md"), ".")]
datas += [(str(root / "gpx2elev/assets"), "gpx2elev/assets")]
datas += collect_data_files("rasterio")
datas += [(str(resources / name), "smoke_data") for name in ("copernicus.tif", "fabdem.tif", "mapterhorn.webp")]

a = Analysis([str(root / "launcher.py")], pathex=[str(root)], binaries=[], datas=datas,
             hiddenimports=collect_submodules("rasterio"),
             hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=["tkinter", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtNetwork"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="gpx2elev", debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          icon=str(assets / "icon.ico") if sys.platform == "win32" else None,
          target_arch=None, codesign_identity=None, entitlements_file=None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="gpx2elev")
if sys.platform == "darwin":
    app = BUNDLE(coll, name="gpx2elev.app", icon=str(assets / "icon.icns"),
                 bundle_identifier="com.nico.gpx2elev", version="0.2.0",
                 info_plist={"NSHighResolutionCapable": True,
                             "LSMinimumSystemVersion": "13.0",
                             "CFBundleDisplayName": "gpx2elev",
                             "CFBundleDocumentTypes": [{"CFBundleTypeName": "Trace GPX", "CFBundleTypeExtensions": ["gpx"],
                                 "CFBundleTypeRole": "Viewer", "LSHandlerRank": "Alternate",
                                 "LSItemContentTypes": ["com.topografix.gpx"]}],
                             "UTImportedTypeDeclarations": [{"UTTypeIdentifier": "com.topografix.gpx", "UTTypeConformsTo": ["public.xml"],
                                 "UTTypeDescription": "Trace GPX", "UTTypeTagSpecification": {"public.filename-extension": ["gpx"],
                                 "public.mime-type": ["application/gpx+xml"]}}]})
