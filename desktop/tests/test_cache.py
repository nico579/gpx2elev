from pathlib import Path
import tempfile
import unittest

from gpx2elev.cache import cache_sizes, clear_cache


class CacheTests(unittest.TestCase):
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
