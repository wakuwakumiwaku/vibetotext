"""Run the embedded macOS history reader with inert AppKit names only."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import types
from typing import Any
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load_source(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.__file__ is not None
    assert Path(module.__file__).resolve() == ROOT / relative
    return module


history = load_source("mac_history_store", "src/vibetotext/history.py")
history_ui = load_source("mac_history_ui", "src/vibetotext/history_ui.py")


def embedded_reader(home):
    # Execute the complete unmodified embedded script, not a copied function.
    # Names imported from AppKit/Foundation are inert; no GUI is instantiated.
    script = history_ui.HISTORY_UI_SCRIPT
    platform_modules = {}
    for node in ast.walk(ast.parse(script)):
        if isinstance(node, ast.ImportFrom) and node.module in ("AppKit", "Foundation"):
            module = platform_modules.setdefault(node.module, types.ModuleType(node.module))
            for alias in node.names:
                setattr(module, alias.name, type("NSObject", (), {}) if alias.name == "NSObject" else object())
    platform_modules["objc"] = types.ModuleType("objc")
    namespace: dict[str, Any] = {"__name__": "embedded_history_regression"}
    with mock.patch.dict(os.environ, HOME=str(home)), mock.patch.dict(sys.modules, platform_modules):
        exec(compile(script, str(ROOT / "src/vibetotext/history_ui.py") + ":HISTORY_UI_SCRIPT", "exec"), namespace)
    print("EMBEDDED_SOURCE", history_ui.__file__, "HISTORY_FILE", namespace["HISTORY_FILE"])
    return namespace["load_history"]


class MacHistoryTests(unittest.TestCase):
    def seed(self, home, text, timestamp):
        path = home / ".vibetotext/history.db"
        history.TranscriptionHistory(path)
        with sqlite3.connect(path) as conn:
            conn.execute("INSERT INTO entries (text, mode, timestamp, word_count) VALUES (?, ?, ?, ?)",
                         (text, "transcribe", timestamp, len(text.split())))

    def test_current_sqlite_entries_are_visible_and_newest_first(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self.seed(home, "older synthetic words", "2026-01-01T10:00:00")
            self.seed(home, "newer synthetic words", "2026-01-02T10:00:00")
            reader = embedded_reader(home)
            entries = reader()["entries"]
            self.assertEqual([entry["text"] for entry in entries],
                             ["newer synthetic words", "older synthetic words"],
                             "The macOS window must read the database written by the transcription engine")
            self.assertEqual(entries[0]["word_count"], 3)
            self.seed(home, "latest update", "2026-01-03T10:00:00")
            self.assertEqual(reader()["entries"][0]["text"], "latest update")

    def test_migrated_json_does_not_hide_history(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            folder = home / ".vibetotext"
            folder.mkdir()
            (folder / "history.json").write_text(json.dumps({"entries": [{
                "text": "legacy synthetic entry", "mode": "transcribe",
                "timestamp": "2026-01-01T10:00:00", "word_count": 3}]}), encoding="utf-8")
            history.TranscriptionHistory(folder / "history.db")
            self.assertTrue((folder / "history.json.migrated").exists())
            entries = embedded_reader(home)()["entries"]
            self.assertEqual([entry["text"] for entry in entries], ["legacy synthetic entry"],
                             "Migrated history must remain visible after JSON is renamed")

    def test_empty_storage_control(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self.assertEqual(embedded_reader(home)(), {"entries": []})
            history.TranscriptionHistory(home / ".vibetotext/history.db")
            self.assertEqual(embedded_reader(home)(), {"entries": []})


if __name__ == "__main__":
    unittest.main()
