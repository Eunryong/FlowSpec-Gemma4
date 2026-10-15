from __future__ import annotations

from pathlib import Path


class WorkspaceError(RuntimeError):
    pass


class Workspace:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve(self, relative_path: str) -> Path:
        if not relative_path or relative_path == ".":
            return self.root
        candidate = (self.root / relative_path).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise WorkspaceError(f"Path escapes workspace: {relative_path}") from exc
        return candidate

    def relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()
