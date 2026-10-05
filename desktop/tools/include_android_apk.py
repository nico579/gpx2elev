"""Include the already signed and verified Android release in desktop releases."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    manifest = json.loads((Path(__file__).resolve().parents[2] / "android-release.json").read_text(encoding="utf-8"))
    args.directory.mkdir(parents=True, exist_ok=True)
    for name in (manifest["apk"], manifest["verification"]):
        if Path(name).name != name:
            raise ValueError("Nom d'asset Android invalide.")
    with tempfile.TemporaryDirectory() as temporary:
        subprocess.run(["gh", "release", "download", manifest["tag"], "--repo", manifest["repository"],
                        "--pattern", manifest["apk"], "--pattern", manifest["verification"], "--dir", temporary], check=True)
        paths = [(manifest["apk"], manifest["sha256"], manifest["apk"]),
                 (manifest["verification"], manifest["verification_sha256"], "verification-android.json")]
        for name, expected, output in paths:
            path = Path(temporary) / name
            # The release job may use Ubuntu's Python 3.10, unlike app builds.
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            actual = digest.hexdigest()
            if actual != expected:
                raise ValueError(f"SHA-256 incorrect pour {name}.")
            shutil.copy2(path, args.directory / output)
    checksum = f"{manifest['sha256']}  {manifest['apk']}\n"
    (args.directory / "SHA256SUMS-android.txt").write_text(checksum, encoding="utf-8", newline="\n")
    print(f"APK Android {manifest['version']} vérifié et ajouté : {manifest['apk']}")


if __name__ == "__main__":
    main()
