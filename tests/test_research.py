from __future__ import annotations

import json
from pathlib import Path

import pytest

from gemma_agent.config import Config
from gemma_agent.research_runner import ExperimentRunner
from gemma_agent.research_store import ResearchError
from gemma_agent.workspace import Workspace, WorkspaceError


VALID_DESIGN = {
    key: []
    for key in (
        "goals", "actors", "user_flows", "domain_entities", "states",
        "business_rules", "ui_views", "edge_cases", "design_decisions",
        "assumptions", "unresolved_items",
    )
}


class FakeHttpClient:
    def close(self):
        pass


class FakeDesigner:
    instances = []
    response = VALID_DESIGN

    def __init__(self, config):
        self.config = config
        self.client = FakeHttpClient()
        self.calls = []
        self.instances.append(self)

    def chat(self, messages, tools):
        self.calls.append((messages, tools))
        return (
            {"role": "assistant", "content": json.dumps(self.response)},
            {
                "input_tokens": 31,
                "output_tokens": 19,
                "total_tokens": 50,
                "ttft_ms": 12.5,
                "first_text_ms": 12.5,
                "prefill_ms": 8.25,
                "generation_ms": 20.0,
                "total_latency_ms": 33.0,
                "generation_tokens_per_second": 950.0,
            },
        )


class FakeAgent:
    instances = []

    def __init__(self, *, workspace_path, config, system_prompt, trace_path, run_id, trace_metadata):
        self.workspace_path = Path(workspace_path)
        self.trace_path = Path(trace_path)
        self.run_id = run_id
        self.trace_metadata = trace_metadata
        self.system_prompt = system_prompt
        self.client = FakeHttpClient()
        self.requests = []
        self.instances.append(self)

    def run(self, request):
        self.requests.append(request)
        self.workspace_path.mkdir(parents=True, exist_ok=True)
        (self.workspace_path / "implementation.txt").write_text(
            self.trace_metadata["stage"], encoding="utf-8"
        )
        fields = {
            "run_id": self.run_id,
            "turn_id": 1,
            **self.trace_metadata,
        }
        events = [
            {"event": "user_request", **fields, "content": request},
            {"event": "model_response", **fields, "step": 1, "message": {"role": "assistant", "content": "done"}},
            {"event": "tool_call", **fields, "name": "write_file", "arguments": {"path": "implementation.txt"}},
            {"event": "tool_result", **fields, "name": "write_file", "elapsed_ms": 4.0, "result": "written"},
            {
                "event": "turn_metrics", **fields, "status": "completed", "model_calls": 2,
                "tool_calls": 1, "input_tokens": 90, "output_tokens": 30, "total_tokens": 120,
                "token_usage_complete": True, "ttft_ms": 21.0, "first_text_ms": 23.0,
                "prefill_ms": 11.0, "generation_ms": 40.0, "total_latency_ms": 63.0,
                "generation_tokens_per_second": 750.0, "tool_time_ms": 4.0,
                "agent_turn_ms": 71.0,
            },
        ]
        self.trace_path.parent.mkdir(parents=True, exist_ok=True)
        with self.trace_path.open("a", encoding="utf-8") as stream:
            for event in events:
                stream.write(json.dumps(event) + "\n")
        return "done"


@pytest.fixture(autouse=True)
def reset_fakes():
    FakeDesigner.instances = []
    FakeDesigner.response = VALID_DESIGN
    FakeAgent.instances = []


def make_runner(tmp_path: Path, *, source_workspace: Path | None = None) -> ExperimentRunner:
    root = tmp_path / "research"
    return ExperimentRunner(
        root,
        config=Config(seed=100, context_length=8192),
        project_root=tmp_path,
        source_workspace=source_workspace,
        client_factory=FakeDesigner,
        agent_factory=FakeAgent,
    )


def brief_file(tmp_path: Path) -> Path:
    path = tmp_path / "brief.md"
    path.write_text("Shared service brief", encoding="utf-8")
    return path


def test_repetitions_are_isolated_fresh_and_record_hashes_and_costs(tmp_path):
    source = tmp_path / "starter"
    source.mkdir()
    (source / "app.py").write_text("starter", encoding="utf-8")
    (source / "research" / "hidden" / "tests").mkdir(parents=True)
    (source / "research" / "hidden" / "tests" / "secret.txt").write_text("hidden", encoding="utf-8")
    runner = make_runner(tmp_path, source_workspace=source)
    condition = runner.research_root / "conditions/track1/generic.md"
    condition.write_text("selected condition only", encoding="utf-8")
    (runner.research_root / "conditions/track1/profile_edge_case.md").write_text(
        "must never be included", encoding="utf-8"
    )

    runs = runner.run_full(
        track="track1", condition="generic", brief=brief_file(tmp_path), repetitions=2, seed=13
    )

    assert len(runs) == 2
    assert len(FakeDesigner.instances) == 2
    assert len(FakeAgent.instances) == 2
    assert runs[0]["run_id"] != runs[1]["run_id"]
    assert runs[0]["model_configuration"]["seed"] == 13
    assert runs[1]["model_configuration"]["seed"] == 14
    assert runs[0]["brief_file"]["sha256"] == runs[1]["brief_file"]["sha256"]
    assert runs[0]["condition_file"]["sha256"] == runs[1]["condition_file"]["sha256"]

    workspaces = [Path(run["implementation_workspace"]["path"]) for run in runs]
    assert workspaces[0] != workspaces[1]
    assert all((workspace / "app.py").is_file() for workspace in workspaces)
    assert all(not (workspace / "research").exists() for workspace in workspaces)
    assert workspaces[0].joinpath("implementation.txt").read_text() == "implementation"

    for run, workspace in zip(runs, workspaces):
        trace = [json.loads(line) for line in (workspace / ".agent/trace.jsonl").read_text().splitlines()]
        metrics = json.loads((runner.research_root / "runs" / run["run_id"] / "metrics/total.json").read_text())
        design_request = FakeDesigner.instances[runs.index(run)].calls[0][0][-1]["content"]
        coder_request = FakeAgent.instances[runs.index(run)].requests[0]
        assert "selected condition only" in design_request
        assert "must never be included" not in design_request
        assert "selected condition only" not in coder_request
        assert "must never be included" not in coder_request
        assert json.dumps(VALID_DESIGN, ensure_ascii=False, indent=2) in coder_request
        assert FakeDesigner.instances[runs.index(run)].calls[0][1] == []
        assert trace[0]["run_id"] == run["run_id"]
        assert trace[0]["stage"] == "implementation"
        assert metrics["design_cost"]["input_tokens"] == 31
        assert metrics["implementation_cost"]["tool_calls"] == 1
        assert metrics["implementation_cost"]["tool_time_ms"] == 4.0
        assert metrics["cumulative_total_cost"]["total_tokens"] == 170
        assert metrics["cumulative_total_cost"]["prefill_ms"] == pytest.approx(19.25)

    assert runner.verify_group(track="track1", condition="generic")["valid"]
    with pytest.raises(WorkspaceError):
        Workspace(workspaces[0]).resolve("../research/hidden/tests/secret.txt")


def test_invalid_design_is_recorded_and_coder_never_starts(tmp_path):
    FakeDesigner.response = {"goals": []}
    runner = make_runner(tmp_path)
    result = runner.run_full(
        track="track1", condition="generic", brief=brief_file(tmp_path)
    )[0]
    run_dir = runner.research_root / "runs" / result["run_id"]
    validation = json.loads((run_dir / "design/validation.json").read_text())
    assert validation["valid"] is False
    assert validation["auto_corrected"] is False
    assert result["implementation_status"] == "not_started"
    assert FakeAgent.instances == []


def test_custom_research_root_is_excluded_when_nested_in_source_workspace(tmp_path):
    source = tmp_path / "project"
    source.mkdir()
    (source / "app.py").write_text("starter", encoding="utf-8")
    research_root = source / "study-data"
    runner = ExperimentRunner(
        research_root,
        config=Config(),
        project_root=tmp_path,
        source_workspace=source,
        client_factory=FakeDesigner,
        agent_factory=FakeAgent,
    )
    (research_root / "hidden/tests/secret.txt").write_text("secret", encoding="utf-8")
    result = runner.run_full(
        track="track1", condition="generic", brief=brief_file(tmp_path)
    )[0]
    workspace = Path(result["implementation_workspace"]["path"])
    assert (workspace / "app.py").is_file()
    assert not (workspace / "study-data").exists()
    with pytest.raises(ResearchError, match="inside the research data directory"):
        ExperimentRunner(
            research_root,
            source_workspace=research_root / "hidden",
            client_factory=FakeDesigner,
            agent_factory=FakeAgent,
        )


def test_revision_reveals_one_change_after_v1_and_keeps_fresh_sessions(tmp_path):
    runner = make_runner(tmp_path)
    changes = runner.research_root / "hidden/changes"
    (changes / "change_01.md").write_text("first future change", encoding="utf-8")
    (changes / "change_02.md").write_text("second future change", encoding="utf-8")
    run = runner.run_full(track="track2", condition="normal", brief=brief_file(tmp_path))[0]

    after_first = runner.revise(run["run_id"])
    first_request = FakeAgent.instances[-1].requests[0]
    assert "first future change" in first_request
    assert "second future change" not in first_request
    assert after_first["revisions"][0]["stage"] == "revision_1"

    after_second = runner.revise(run["run_id"])
    second_request = FakeAgent.instances[-1].requests[0]
    assert "second future change" in second_request
    assert after_second["revisions"][1]["stage"] == "revision_2"
    assert len({agent.workspace_path for agent in FakeAgent.instances}) == 3
    assert len({id(agent) for agent in FakeAgent.instances}) == 3
    assert (runner.research_root / "runs" / run["run_id"] / "metrics/revision_1.json").is_file()
    assert (runner.research_root / "runs" / run["run_id"] / "metrics/revision_2.json").is_file()


def test_blind_export_strips_condition_and_stores_mapping_under_hidden(tmp_path):
    runner = make_runner(tmp_path)
    run = runner.run_full(track="track1", condition="generic", brief=brief_file(tmp_path))[0]
    destination, mapping = runner.blind_export([run["run_id"]])
    alias = next(iter(mapping))
    assert (destination / alias / "design_spec.json").is_file()
    assert (destination / alias / "evaluation.json").is_file()
    assert not (destination / alias / "condition.md").exists()
    assert runner.research_root.joinpath("hidden/evaluation-maps").joinpath(
        next((runner.research_root / "hidden/evaluation-maps").iterdir()).name
    ).is_file()
    assert runner.list_metadata()[0]["condition"] == "generic"


def test_revise_cannot_reveal_future_change_before_v1(tmp_path):
    runner = make_runner(tmp_path)
    changes = runner.research_root / "hidden/changes"
    (changes / "change_01.md").write_text("not yet", encoding="utf-8")
    run = runner.run_design(track="track2", condition="normal", brief=brief_file(tmp_path))[0]
    with pytest.raises(ResearchError, match="V1 design and implementation"):
        runner.revise(run["run_id"])
    assert not list((runner.research_root / "runs" / run["run_id"] / "inputs/revisions").glob("*.md"))


def test_direct_run_skips_design_stage(tmp_path):
    runner = make_runner(tmp_path)
    run = runner.run_direct(track="track2", condition="normal", brief=brief_file(tmp_path))[0]
    assert run["design_status"] == "skipped"
    assert run["implementation_status"] == "completed"
    assert not (runner.research_root / "runs" / run["run_id"] / "design/design_spec.json").exists()
    assert (runner.research_root / "runs" / run["run_id"] / "implementation").is_dir()
    assert (runner.research_root / "runs" / run["run_id"] / "metrics/implementation.json").is_file()

