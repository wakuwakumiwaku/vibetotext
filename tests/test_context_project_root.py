"""Real Git path discovery and safe search leaf; no Greppy/audio/model runtime."""
from contextlib import contextmanager
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("tested_context", ROOT / "src/vibetotext/context.py")
assert SPEC is not None and SPEC.loader is not None
context = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(context)
assert context.__file__ is not None
assert Path(context.__file__).resolve() == ROOT / "src/vibetotext/context.py"
GIT = shutil.which("git")
assert GIT is not None, "Git is required for the real project-discovery fixture"


@contextmanager
def working_directory(path):
    before = Path.cwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(before)


class ProjectRootTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "Synthetic executable fixture uses POSIX permissions")
    def test_git_root_reaches_search_without_losing_filename_whitespace(self):
        names = ["ordinary", "project with spaces", "project ", "project\t", "project\n", "project\n\n", "project\ninside "]
        with tempfile.TemporaryDirectory(prefix="context-root-") as directory:
            root = Path(directory)
            tools = root / "tools"
            tools.mkdir()
            leaf = tools / "greppy"
            leaf.write_text("#!" + sys.executable + "\nimport json, sys\n"
                            "path = sys.argv[sys.argv.index('-p') + 1]\n"
                            "print(json.dumps({'file_path': path, 'start_line': 1, 'end_line': 1, 'content': 'synthetic search'}))\n",
                            encoding="utf-8")
            leaf.chmod(0o700)
            for name in names:
                with self.subTest(name=repr(name)):
                    project = root / name
                    project.mkdir()
                    init = subprocess.run([GIT, "init", "--quiet", str(project)], capture_output=True, timeout=5)
                    self.assertEqual(init.returncode, 0, init.stderr)
                    nested = project / "nested"
                    nested.mkdir()
                    with working_directory(nested), mock.patch.dict(os.environ, PATH=str(tools) + os.pathsep + os.environ["PATH"]):
                        observed = context.get_project_root()
                        snippets = context.search_context("literal query", limit=2)
                    self.assertEqual(observed, project, "Git's record newline is not part of the directory; filename whitespace is")
                    self.assertEqual(snippets, [{"header": str(project) + ":1-1", "content": ["synthetic search"]}],
                                     "The public search caller must pass the complete literal project path")

    def test_non_repository_still_falls_back_to_current_directory(self):
        with tempfile.TemporaryDirectory(prefix="context-nongit-") as directory, working_directory(directory):
            self.assertEqual(context.get_project_root(), Path(directory))


if __name__ == "__main__":
    unittest.main()
