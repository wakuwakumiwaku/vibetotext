"""Greppy integration for code context."""

import subprocess
import json
import os
from pathlib import Path
from typing import List, Optional


def get_project_root() -> Optional[Path]:
    """Get current project root (git root or cwd)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
        )
        if result.returncode == 0:
            # Remove Git's record terminator, not whitespace in the filename.
            return Path(os.fsdecode(result.stdout.removesuffix(b"\n")))
    except Exception:
        pass
    return Path.cwd()


def search_context(query: str, limit: int = 5) -> List[dict]:
    """
    Search codebase for relevant context using Greppy.

    Args:
        query: Natural language query (the transcribed voice input)
        limit: Max number of results

    Returns:
        List of relevant code snippets
    """
    project_root = get_project_root()

    try:
        # Rust greppy: query first, then options, use --json for reliable parsing
        result = subprocess.run(
            ["greppy", "search", query, "-n", str(limit), "-p", str(project_root), "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return []

        # Parse JSON output (one object per line)
        snippets = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                filepath = item.get("file_path", "")
                start_line = item.get("start_line", 1)
                end_line = item.get("end_line", start_line)
                content = item.get("content", "")

                header = f"{filepath}:{start_line}-{end_line}"
                snippets.append({"header": header, "content": content.split("\n")})
            except json.JSONDecodeError:
                continue

        return snippets

    except subprocess.TimeoutExpired:
        return []
    except FileNotFoundError:
        # Greppy not installed
        return []


def format_context(snippets: List[dict]) -> str:
    """Format code snippets for inclusion in prompt."""
    if not snippets:
        return ""

    parts = ["\n---\nRelevant code context:\n"]

    for snippet in snippets:
        parts.append(f"\n{snippet['header']}")
        parts.append("```")
        parts.append("\n".join(snippet["content"]))
        parts.append("```\n")

    return "\n".join(parts)
