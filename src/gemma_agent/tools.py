from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .workspace import Workspace, WorkspaceError


MAX_READ_CHARS = 10_000
MAX_OUTPUT_CHARS = 3_000


@dataclass
class ToolResult:
    ok: bool
    output: str

    def as_text(self) -> str:
        return json.dumps({"ok": self.ok, "output": self.output}, ensure_ascii=False)


class ToolRegistry:
    def __init__(self, workspace: Workspace):
        self.workspace = workspace
        self._handlers: dict[str, Callable[..., ToolResult]] = {
            "list_files": self.list_files,
            "read_file": self.read_file,
            "write_file": self.write_file,
            "replace_text": self.replace_text,
            "run_tests": self.run_tests,
        }

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "list_files",
                    "description": "List files and directories inside the experiment workspace.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Workspace-relative directory path. Use '.' for root."},
                            "max_depth": {"type": "integer", "minimum": 1, "maximum": 5, "default": 3},
                        },
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a UTF-8 text file inside the experiment workspace.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Workspace-relative file path."}
                        },
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Create or completely overwrite a UTF-8 text file inside the workspace. Parent directories are created automatically.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Workspace-relative file path."},
                            "content": {"type": "string", "description": "Complete new file contents."},
                        },
                        "required": ["path", "content"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "replace_text",
                    "description": "Replace one exact text occurrence in a workspace file. Safer for focused edits than rewriting the whole file.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Workspace-relative file path."},
                            "old": {"type": "string", "description": "Exact existing text to replace."},
                            "new": {"type": "string", "description": "Replacement text."},
                        },
                        "required": ["path", "old", "new"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "run_tests",
                    "description": "Run the workspace test suite automatically. Tries pytest first, then Python unittest discovery. No shell is used.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        handler = self._handlers.get(name)
        if handler is None:
            return ToolResult(False, f"Unknown tool: {name}")
        if isinstance(arguments, dict) and "path" in arguments and isinstance(arguments["path"], str):
            clean_p = arguments["path"]
            for token in ("<tool_call|", "<|tool_call|>", "<|channel>", "}"):
                if token in clean_p:
                    clean_p = clean_p.split(token)[0]
            arguments["path"] = clean_p.strip()
        try:
            return handler(**arguments)
        except (WorkspaceError, OSError, ValueError, TypeError) as exc:
            return ToolResult(False, f"{type(exc).__name__}: {exc}")
        except Exception as exc:  # Keep the research loop alive and log the failure.
            return ToolResult(False, f"Unexpected {type(exc).__name__}: {exc}")

    def list_files(self, path: str = ".", max_depth: int = 3) -> ToolResult:
        base = self.workspace.resolve(path)
        if not base.exists():
            return ToolResult(False, f"Not found: {path}")
        if not base.is_dir():
            return ToolResult(False, f"Not a directory: {path}")

        max_depth = max(1, min(int(max_depth), 5))
        rows: list[str] = []
        for item in sorted(base.rglob("*")):
            rel_to_base = item.relative_to(base)
            if len(rel_to_base.parts) > max_depth:
                continue
            rel = self.workspace.relative(item)
            suffix = "/" if item.is_dir() else ""
            rows.append(rel + suffix)
            if len(rows) >= 1000:
                rows.append("... truncated at 1000 entries")
                break
        return ToolResult(True, "\n".join(rows) if rows else "(empty)")

    def read_file(self, path: str) -> ToolResult:
        target = self.workspace.resolve(path)
        if not target.is_file():
            return ToolResult(False, f"Not a file: {path}")
        text = target.read_text(encoding="utf-8")
        if len(text) > MAX_READ_CHARS:
            text = text[:MAX_READ_CHARS] + "\n... [truncated]"
        return ToolResult(True, text)

    def write_file(self, path: str, content: str) -> ToolResult:
        target = self.workspace.resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return ToolResult(True, f"Wrote {len(content)} chars to {self.workspace.relative(target)}")

    def replace_text(self, path: str, old: str, new: str) -> ToolResult:
        target = self.workspace.resolve(path)
        if not target.is_file():
            return ToolResult(False, f"Not a file: {path}")
        text = target.read_text(encoding="utf-8")
        count = text.count(old)
        if count == 0:
            return ToolResult(False, "Exact old text was not found.")
        if count > 1:
            return ToolResult(False, f"Old text occurs {count} times; provide a more specific match.")
        target.write_text(text.replace(old, new, 1), encoding="utf-8")
        return ToolResult(True, f"Updated {path}")

    def run_tests(self) -> ToolResult:
        candidates = [
            ["python3", "-m", "pytest", "-q", "--tb=short", "--maxfail=3"],
            ["python3", "-m", "unittest", "discover", "-v"],
        ]
        reports: list[str] = []
        for cmd in candidates:
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=self.workspace.root,
                    text=True,
                    capture_output=True,
                    timeout=120,
                    check=False,
                )
            except FileNotFoundError:
                reports.append(f"Missing executable: {cmd[0]}")
                continue
            except subprocess.TimeoutExpired:
                return ToolResult(False, f"Timed out after 120s: {' '.join(cmd)}")

            output = ((proc.stdout or "") + (proc.stderr or ""))[-MAX_OUTPUT_CHARS:]
            if proc.returncode == 5:
                output += "\n[Hint: pytest exit 5 means no tests were collected. Ensure test files match 'test_*.py' or '*_test.py' and contain 'test_*' functions.]"
            reports.append(f"$ {' '.join(cmd)}\nexit={proc.returncode}\n{output}")
            # pytest missing is a special case: fall through to unittest.
            if cmd[2:4] == ["pytest", "-q"] and "No module named pytest" in output:
                continue
            return ToolResult(proc.returncode == 0, reports[-1])

        return ToolResult(False, "\n\n".join(reports) or "No test runner available")
