from pathlib import Path

import pytest

from gemma_agent.workspace import Workspace, WorkspaceError


def test_workspace_blocks_parent_escape(tmp_path: Path):
    ws = Workspace(tmp_path / "work")
    with pytest.raises(WorkspaceError):
        ws.resolve("../secret.txt")


def test_workspace_allows_nested_path(tmp_path: Path):
    ws = Workspace(tmp_path / "work")
    assert ws.resolve("src/app.py") == (ws.root / "src/app.py").resolve()
