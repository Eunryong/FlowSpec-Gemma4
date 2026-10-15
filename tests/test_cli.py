import sys

import pytest

from gemma_agent import cli


@pytest.mark.parametrize("stop", ["exit", "quit", EOFError, KeyboardInterrupt])
@pytest.mark.parametrize("interactive_option", [[], ["--interactive"]])
def test_interactive_reuses_agent_and_stops_cleanly(
    monkeypatch, tmp_path, capsys, stop, interactive_option
):
    constructed = []
    requests = []
    prompts = []

    class FakeAgent:
        def __init__(self, **kwargs):
            constructed.append(kwargs)

        def run(self, request):
            requests.append(request)
            return f"reply to {request}"

    inputs = iter(["first request", "second request", stop])

    def fake_input(prompt):
        prompts.append(prompt)
        value = next(inputs)
        if isinstance(value, type) and issubclass(value, BaseException):
            raise value
        return value

    monkeypatch.setattr(cli, "CodingAgent", FakeAgent)
    monkeypatch.setattr(
        sys,
        "argv",
        ["gemma-agent", "--workspace", str(tmp_path), *interactive_option],
    )
    monkeypatch.setattr("builtins.input", fake_input)

    cli.main()

    assert len(constructed) == 1
    assert requests == ["first request", "second request"]
    assert prompts == ["gemma> ", "gemma> ", "gemma> "]
    output = capsys.readouterr().out
    assert "agent> reply to first request" in output
    assert "agent> reply to second request" in output


def test_prompt_mode_remains_one_shot(monkeypatch, tmp_path, capsys):
    requests = []

    class FakeAgent:
        def __init__(self, **kwargs):
            pass

        def run(self, request):
            requests.append(request)
            return "one-shot response"

    monkeypatch.setattr(cli, "CodingAgent", FakeAgent)
    monkeypatch.setattr(
        sys,
        "argv",
        ["gemma-agent", "--workspace", str(tmp_path), "--prompt", "do the task"],
    )

    cli.main()

    assert requests == ["do the task"]
    assert capsys.readouterr().out.strip() == "one-shot response"


def test_prompt_and_interactive_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        cli.parser().parse_args(["--workspace", ".", "--prompt", "task", "--interactive"])



def test_trace_labels_are_passed_to_agent_without_changing_prompt(monkeypatch, tmp_path):
    created = []

    class FakeAgent:
        def __init__(self, **kwargs):
            created.append(kwargs)

        def run(self, request):
            return "done"

    monkeypatch.setattr(cli, "CodingAgent", FakeAgent)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "gemma-agent",
            "--workspace",
            str(tmp_path),
            "--prompt",
            "make a function",
            "--run-id",
            "run-1",
            "--task-id",
            "task-1",
            "--condition",
            "generic",
            "--stage",
            "implementation",
        ],
    )

    cli.main()

    assert created[0]["run_id"] == "run-1"
    assert created[0]["trace_metadata"] == {
        "task_id": "task-1",
        "condition": "generic",
        "stage": "implementation",
    }
