from pathlib import Path

from gemma_agent.tools import ToolRegistry
from gemma_agent.workspace import Workspace


def test_write_read_replace(tmp_path: Path):
    registry = ToolRegistry(Workspace(tmp_path / "work"))
    assert registry.write_file("a.txt", "hello world").ok
    assert registry.read_file("a.txt").output == "hello world"
    assert registry.replace_text("a.txt", "world", "gemma").ok
    assert registry.read_file("a.txt").output == "hello gemma"


def test_replace_requires_unique_match(tmp_path: Path):
    registry = ToolRegistry(Workspace(tmp_path / "work"))
    registry.write_file("a.txt", "x x")
    result = registry.replace_text("a.txt", "x", "y")
    assert not result.ok
