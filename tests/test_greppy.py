"""Greppy attachment tests run without audio, models, or a Greppy installation."""
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from vibetotext import greppy


class GreppyContextTests(unittest.TestCase):
    def test_read_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample file.py"
            path.write_text("print('café')\n", encoding="utf-8")
            self.assertEqual(greppy.read_file_content(str(path)), "print('café')\n")

    def test_context_contains_readable_files_and_skips_missing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.py"
            path.write_text("answer = 42\n", encoding="utf-8")
            with mock.patch.object(Path, "home", return_value=Path(directory)):
                context = greppy.format_files_for_context([(str(path), 1), (str(path) + ".missing", 1)])
            self.assertEqual(context, "\n\n### ~/sample.py\n```\nanswer = 42\n\n```")

    def test_missing_file_stays_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(greppy.read_file_content(str(Path(directory) / "missing")), "")

    def test_truncation_only_when_more_lines_exist(self):
        for contents, expected in [("one\ntwo\n", "one\ntwo\n"),
                                   ("one\ntwo\nthree\n", "one\ntwo\n\n... (truncated at 2 lines)")]:
            with self.subTest(contents=contents), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "sample.txt"
                path.write_text(contents, encoding="utf-8")
                self.assertEqual(greppy.read_file_content(str(path), max_lines=2), expected)

    def test_reader_does_not_consume_entire_large_file(self):
        class GuardedLines(io.StringIO):
            def readlines(self, *args, **kwargs):
                raise AssertionError("Context reader must not read the entire file")
            def __next__(self):
                self.lines_read += 1
                if self.lines_read > 3:
                    raise AssertionError("At most the requested lines plus one lookahead may be read")
                return super().__next__()
        stream = GuardedLines("one\ntwo\nthree\nfour\n")
        stream.lines_read = 0
        with mock.patch("builtins.open", return_value=stream):
            with mock.patch.object(Path, "exists", return_value=True):
                self.assertIn("truncated at 2 lines", greppy.read_file_content("synthetic.txt", max_lines=2))
        self.assertEqual(stream.lines_read, 3)

    def test_nonpositive_limit_produces_no_context(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.txt"
            path.write_text("one\ntwo\n", encoding="utf-8")
            for limit in (0, -1):
                self.assertEqual(greppy.read_file_content(str(path), max_lines=limit), "")


if __name__ == "__main__":
    unittest.main()
