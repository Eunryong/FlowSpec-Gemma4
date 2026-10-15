from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESEARCH_ROOT = PROJECT_ROOT / "research"
RESEARCH_DIRECTORIES = (
    "briefs",
    "conditions/track1",
    "conditions/track2",
    "prompts",
    "schemas",
    "runs",
    "hidden/tests",
    "hidden/changes",
    "hidden/evaluation-maps",
    "evaluation",
    "scripts",
)
RESEARCH_TEMPLATES = (
    "briefs/README.md",
    "briefs/placeholder.md",
    "conditions/track1/generic.md",
    "conditions/track1/profile_edge_case.md",
    "conditions/track1/profile_compensated.md",
    "conditions/track2/normal.md",
    "conditions/track2/extensible.md",
    "conditions/track2/revision_aware.md",
    "prompts/designer-common.md",
    "prompts/coder-common.md",
    "schemas/design-specification.schema.json",
    "runs/README.md",
    "hidden/tests/README.md",
    "hidden/changes/README.md",
    "evaluation/README.md",
    "evaluation/result.schema.json",
    "scripts/README.md",
)


class ResearchError(RuntimeError):
    pass


def timestamp_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def sha256_tree(root: str | Path) -> str:
    base = Path(root).resolve()
    digest = hashlib.sha256()
    if not base.exists():
        raise FileNotFoundError(base)
    for path in sorted(base.rglob("*"), key=lambda item: item.relative_to(base).as_posix()):
        relative = path.relative_to(base)
        if any(part in {".git", ".agent", ".venv", "node_modules", "__pycache__"} for part in relative.parts):
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        if path.is_symlink():
            digest.update(os.readlink(path).encode("utf-8"))
        elif path.is_file():
            digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def atomic_write_json(path: str | Path, data: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, target)


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def initialize_research_layout(research_root: str | Path = DEFAULT_RESEARCH_ROOT) -> Path:
    root = Path(research_root).expanduser().resolve()
    for relative in RESEARCH_DIRECTORIES:
        (root / relative).mkdir(parents=True, exist_ok=True)
    template_root = DEFAULT_RESEARCH_ROOT
    if root != template_root.resolve():
        for relative in RESEARCH_TEMPLATES:
            source = template_root / relative
            destination = root / relative
            if source.is_file() and not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
    return root


def resolve_condition_file(research_root: str | Path, track: str, condition: str) -> Path:
    if not track or Path(track).name != track or track.startswith("."):
        raise ResearchError(f"Invalid track name: {track!r}")
    if not condition or Path(condition).name != condition or condition.startswith("."):
        raise ResearchError(f"Invalid condition name: {condition!r}")
    candidate = (Path(research_root) / "conditions" / track / f"{condition}.md").resolve()
    expected_parent = (Path(research_root) / "conditions" / track).resolve()
    if candidate.parent != expected_parent:
        raise ResearchError("Condition path escaped its track directory")
    if not candidate.is_file():
        raise ResearchError(f"No condition file for {track}/{condition}: {candidate}")
    return candidate


def git_commit(project_root: str | Path = PROJECT_ROOT) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            text=True,
            capture_output=True,
            timeout=2,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    commit = result.stdout.strip()
    return commit if result.returncode == 0 and commit else None


def copy_workspace(
    source: str | Path | None,
    destination: str | Path,
    *,
    exclude_paths: tuple[str, ...] = (),
) -> None:
    target = Path(destination)
    target.mkdir(parents=True, exist_ok=True)
    if source is None:
        return
    origin = Path(source).expanduser().resolve()
    if not origin.is_dir():
        raise ResearchError(f"Source workspace is not a directory: {origin}")
    # The experiment harness and its condition/hidden-evaluation files must not
    # become part of a model-visible implementation workspace.
    excluded = {Path(item).as_posix().strip("/") for item in exclude_paths}

    def ignore(directory: str, names: list[str]) -> set[str]:
        relative_dir = Path(directory).resolve().relative_to(origin)
        ignored = {
            name for name in names
            if name in {".git", ".agent", ".venv", "node_modules", "__pycache__", "research"}
        }
        for name in names:
            relative_item = (relative_dir / name).as_posix().removeprefix("./")
            if relative_item in excluded:
                ignored.add(name)
        return ignored

    shutil.copytree(origin, target, dirs_exist_ok=True, symlinks=True, ignore=ignore)


def load_run_metadata(research_root: str | Path, run_id: str) -> tuple[Path, dict[str, Any]]:
    if not run_id or Path(run_id).name != run_id:
        raise ResearchError(f"Invalid run id: {run_id!r}")
    run_dir = Path(research_root) / "runs" / run_id
    metadata_path = run_dir / "metadata.json"
    if not metadata_path.is_file():
        raise ResearchError(f"Run not found: {run_id}")
    metadata = read_json(metadata_path)
    if metadata.get("run_id") != run_id:
        raise ResearchError(f"Run metadata id mismatch: {run_id}")
    return run_dir, metadata


def write_run_metadata(run_dir: str | Path, metadata: dict[str, Any]) -> None:
    atomic_write_json(Path(run_dir) / "metadata.json", metadata)
