import json
from pathlib import Path

import pytest

from gemma_agent.agent import CodingAgent
from gemma_agent.config import Config


class ScriptedClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def chat(self, messages, tools):
        self.calls.append([dict(message) for message in messages])
        return next(self.responses)


def test_run_keeps_history_and_records_turn_metrics(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "note.txt").write_text("remember this", encoding="utf-8")
    trace_path = tmp_path / "trace.jsonl"
    tool_call = {
        "id": "call-1",
        "type": "function",
        "function": {"name": "read_file", "arguments": '{"path":"note.txt"}'},
    }
    client = ScriptedClient(
        [
            (
                {"role": "assistant", "content": None, "tool_calls": [tool_call]},
                {
                    "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
                    "input_tokens": 12,
                    "output_tokens": 5,
                    "total_tokens": 17,
                    "ttft_ms": 50,
                    "first_text_ms": None,
                    "generation_ms": 80,
                    "total_latency_ms": 130,
                },
            ),
            (
                {"role": "assistant", "content": "The note says remember this."},
                {
                    "usage": {"prompt_tokens": 18, "completion_tokens": 8, "total_tokens": 26},
                    "input_tokens": 18,
                    "output_tokens": 8,
                    "total_tokens": 26,
                    "ttft_ms": 40,
                    "first_text_ms": 40,
                    "generation_ms": 60,
                    "total_latency_ms": 100,
                },
            ),
            (
                {"role": "assistant", "content": "I remember: remember this."},
                {
                    "usage": {"prompt_tokens": 30, "completion_tokens": 6, "total_tokens": 36},
                    "input_tokens": 30,
                    "output_tokens": 6,
                    "total_tokens": 36,
                    "ttft_ms": 20,
                    "first_text_ms": 20,
                    "generation_ms": 40,
                    "total_latency_ms": 60,
                },
            ),
        ]
    )
    agent = CodingAgent(
        workspace,
        config=Config(max_steps=3),
        trace_path=trace_path,
        run_id="run-test",
        trace_metadata={"task_id": "case-1", "condition": "generic", "stage": "implementation"},
    )
    agent.client = client

    assert agent.run("Read note.txt") == "The note says remember this."
    assert agent.run("What did the note say?") == "I remember: remember this."

    assert client.calls[0][-1] == {"role": "user", "content": "Read note.txt"}
    second_turn_messages = client.calls[2]
    assert {"role": "user", "content": "Read note.txt"} in second_turn_messages
    assert {"role": "user", "content": "What did the note say?"} == second_turn_messages[-1]
    assert any(
        message.get("role") == "tool" and "remember this" in message["content"]
        for message in second_turn_messages
    )
    assert any(
        message.get("content") == "The note says remember this."
        for message in second_turn_messages
    )

    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert sum(event["event"] == "user_request" for event in events) == 2
    assert sum(event["event"] == "model_response" for event in events) == 3
    tool_result = next(event for event in events if event["event"] == "tool_result")
    assert tool_result["name"] == "read_file"
    assert "remember this" in tool_result["result"]
    assert tool_result["elapsed_ms"] >= 0

    metrics = [event for event in events if event["event"] == "turn_metrics"]
    assert len(metrics) == 2
    first_turn = metrics[0]
    assert first_turn["run_id"] == "run-test"
    assert first_turn["turn_id"] == 1
    assert first_turn["task_id"] == "case-1"
    assert first_turn["condition"] == "generic"
    assert first_turn["stage"] == "implementation"
    assert first_turn["status"] == "completed"
    assert first_turn["input_tokens"] == 30
    assert first_turn["output_tokens"] == 13
    assert first_turn["total_tokens"] == 43
    assert first_turn["ttft_ms"] >= 50
    assert first_turn["first_text_ms"] is not None
    assert first_turn["generation_ms"] == 140
    assert first_turn["total_latency_ms"] == 230
    assert first_turn["tool_calls"] == 1
    assert first_turn["tool_time_ms"] >= 0
    assert first_turn["agent_turn_ms"] >= first_turn["tool_time_ms"]
    assert first_turn["generation_tokens_per_second"] is not None
    assert metrics[1]["turn_id"] == 2
    assert metrics[1]["input_tokens"] == 30
    assert metrics[1]["output_tokens"] == 6
    assert metrics[1]["tool_calls"] == 0



def test_failed_model_request_still_records_turn_metrics(tmp_path: Path):
    trace_path = tmp_path / "trace.jsonl"
    agent = CodingAgent(tmp_path / "workspace", trace_path=trace_path)

    class FailingClient:
        def chat(self, messages, tools):
            raise TimeoutError("model request timed out")

    agent.client = FailingClient()

    with pytest.raises(TimeoutError):
        agent.run("try this")

    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    model_error = next(event for event in events if event["event"] == "model_error")
    metrics = next(event for event in events if event["event"] == "turn_metrics")
    assert model_error["error_type"] == "TimeoutError"
    assert model_error["total_latency_ms"] >= 0
    assert metrics["status"] == "failed"
    assert metrics["error_type"] == "TimeoutError"
    assert metrics["model_calls"] == 1
    assert metrics["input_tokens"] is None
    assert metrics["output_tokens"] is None
    assert metrics["total_latency_ms"] >= 0
    assert metrics["agent_turn_ms"] >= metrics["total_latency_ms"]
