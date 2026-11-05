"""SQLite migration tests use explicit temporary databases, never user history."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
from pathlib import Path
import threading
import tempfile
import unittest
from unittest import mock

from vibetotext import history

ROOT = Path(__file__).resolve().parents[1]
assert Path(history.__file__).resolve() == ROOT / "src/vibetotext/history.py"


class HistoryMigrationTests(unittest.TestCase):
    def write_history(self, path):
        path.with_suffix(".json").write_text(json.dumps({"entries": [{
            "text": "synthetic migration entry", "mode": "transcribe",
            "timestamp": datetime(2025, 1, 2, 3, 4, 5).isoformat(), "word_count": 3
        }]}), encoding="utf-8")

    def test_concurrent_initializers_import_legacy_history_once(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.db"
            self.write_history(path)
            original_load = json.load
            second_reader = threading.Event()
            lock = threading.Lock()
            reads = 0
            def overlap_read(stream, *args, **kwargs):
                nonlocal reads
                data = original_load(stream, *args, **kwargs)
                with lock:
                    reads += 1
                    first = reads == 1
                if first:
                    # OLD releases its read connection before loading JSON, so a
                    # second initializer can also observe an empty database.
                    # GREEN holds a write reservation, so this bounded wait ends
                    # without a second load and that initializer then sees data.
                    second_reader.wait(timeout=1)
                else:
                    second_reader.set()
                return data
            with mock.patch.object(history.json, "load", side_effect=overlap_read):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures = [pool.submit(history.TranscriptionHistory, path) for _ in range(2)]
                    stores = [future.result(timeout=10) for future in futures]
            for store in stores:
                entries = store.get_entries()
                self.assertEqual(len(entries), 1, "Concurrent migration must not duplicate legacy entries")
                self.assertEqual(entries[0]["text"], "synthetic migration entry")
            self.assertTrue(path.with_suffix(".json.migrated").exists())
            self.assertFalse(path.with_suffix(".json").exists())

    def test_single_initializer_and_reopen_keep_one_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.db"
            self.write_history(path)
            first = history.TranscriptionHistory(path)
            self.assertEqual(len(first.get_entries()), 1)
            second = history.TranscriptionHistory(path)
            self.assertEqual(second.get_entries(), first.get_entries())
            self.assertEqual(second.get_entries()[0]["timestamp"], "2025-01-02T03:04:05")

    def test_existing_database_is_not_merged_with_legacy_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.db"
            self.write_history(path)
            first = history.TranscriptionHistory(path)
            self.write_history(path)
            before = first.get_entries()
            self.assertEqual(history.TranscriptionHistory(path).get_entries(), before)
            self.assertTrue(path.with_suffix(".json").exists())


if __name__ == "__main__":
    unittest.main()
