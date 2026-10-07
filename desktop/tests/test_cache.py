import errno
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from gpx2elev.cache import cache_sizes, clear_cache
from gpx2elev.providers import atomic_write, trim_cache


class CacheTests(unittest.TestCase):
    def test_failed_atomic_write_removes_temporary_and_preserves_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "tile.tif"
            target.write_bytes(b"original")
            factory = tempfile.NamedTemporaryFile

            def failing_file(**kwargs):
                stream = factory(**kwargs)
                write = stream.write
                def fail(data):
                    write(data[:3])
                    raise OSError(errno.ENOSPC, "disk full")
                stream.write = fail
                return stream

            with patch("gpx2elev.providers.tempfile.NamedTemporaryFile", side_effect=failing_file):
                with self.assertRaises(OSError):
                    atomic_write(target, b"replacement")
            self.assertEqual(target.read_bytes(), b"original")
            self.assertEqual(list(root.glob("*.part")), [])

    def test_trim_removes_old_partials_and_preserves_active_and_recent_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / "abandoned.part"
            recent = root / "recent.part"
            old.write_bytes(b"old")
            recent.write_bytes(b"recent")
            old_time = time.time() - 48 * 60 * 60
            os.utime(old, (old_time, old_time))
            started, release = threading.Event(), threading.Event()
            active, failures = [], []
            factory = tempfile.NamedTemporaryFile

            def delayed_file(**kwargs):
                stream = factory(**kwargs)
                active.append(Path(stream.name))
                write = stream.write
                def delay(data):
                    os.utime(stream.name, (old_time, old_time))
                    started.set()
                    if not release.wait(5):
                        raise TimeoutError("writer was not released")
                    return write(data)
                stream.write = delay
                return stream

            def write_file():
                try:
                    atomic_write(root / "complete.tif", b"finished")
                except Exception as exc:
                    failures.append(exc)

            with patch("gpx2elev.providers.tempfile.NamedTemporaryFile", side_effect=delayed_file):
                worker = threading.Thread(target=write_file)
                worker.start()
                try:
                    self.assertTrue(started.wait(5))
                    trim_cache(root, 0)
                    self.assertFalse(old.exists())
                    self.assertTrue(recent.exists())
                    self.assertTrue(active[0].exists())
                finally:
                    release.set()
                    worker.join(5)
            self.assertFalse(worker.is_alive())
            self.assertEqual(failures, [])
            self.assertEqual((root / "complete.tif").read_bytes(), b"finished")

    def test_clear_only_downloads_including_partial_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, data in {'profiles/a.profile': b'123', 'tiles/sub/b.tif': b'4567',
                               'tiles/interrupted.part': b'89', 'last.gpx': b'gpx',
                               'settings.json': b'{}', 'result.csv': b'result'}.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            self.assertEqual(cache_sizes(root), {'profiles': 3, 'tiles': 6})
            clear_cache(root)
            self.assertEqual(cache_sizes(root), {'profiles': 0, 'tiles': 0})
            clear_cache(root)
            self.assertEqual((root / 'last.gpx').read_bytes(), b'gpx')
            self.assertEqual((root / 'settings.json').read_bytes(), b'{}')
            self.assertEqual((root / 'result.csv').read_bytes(), b'result')

    def test_symlink_does_not_remove_or_count_external_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'outside').mkdir()
            (root / 'outside/keep').write_bytes(b'keep')
            (root / 'tiles').mkdir()
            try:
                (root / 'tiles/link').symlink_to(root / 'outside', target_is_directory=True)
            except OSError:
                self.skipTest('Symlink creation requires privileges on this Windows host')
            self.assertEqual(cache_sizes(root), {'profiles': 0, 'tiles': 0})
            clear_cache(root)
            self.assertFalse((root / 'tiles/link').exists())
            self.assertEqual((root / 'outside/keep').read_bytes(), b'keep')
