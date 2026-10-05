"""Manage downloaded data only; never touch the GPX, settings or exports."""
import os
from pathlib import Path


def cache_files(directory):
    def fail(error):
        raise error

    for name in ("profiles", "tiles"):
        root = Path(directory) / name
        if root.is_symlink():
            yield root
            continue
        if not root.exists():
            continue
        for folder, dirs, files in os.walk(root, followlinks=False, onerror=fail):
            for child in dirs[:]:
                path = Path(folder) / child
                if path.is_symlink():
                    dirs.remove(child)
                    yield path
            for child in files:
                yield Path(folder) / child


def cache_sizes(directory):
    sizes = {"profiles": 0, "tiles": 0}
    base = Path(directory)
    for path in cache_files(base):
        if not path.is_symlink():
            sizes[path.relative_to(base).parts[0]] += path.stat().st_size
    return sizes


def clear_cache(directory):
    # Unlink files and links, including abandoned .part files; do not follow links.
    # Empty directories are harmless and reusable by the readers.
    for path in cache_files(directory):
        path.unlink(missing_ok=True)
