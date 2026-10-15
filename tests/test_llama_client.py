import json

from gemma_agent.config import Config
from gemma_agent.llama_client import LlamaClient


class FakeResponse:
    def __init__(self, lines):
        self.lines = lines

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def raise_for_status(self):
        return None

    def iter_lines(self):
        return iter(self.lines)


def _event(payload):
    return "data: " + json.dumps(payload)


def test_stream_reassembles_tool_calls_and_captures_timing(monkeypatch):
    events = [
        _event({"id": "response-1", "choices": [{"delta": {"role": "assistant"}, "finish_reason": None}]}),
        _event({"choices": [{"delta": {"content": "Checking."}, "finish_reason": None}]}),
        _event({
            "choices": [{
                "delta": {
                    "tool_calls": [{
                        "index": 0,
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": '{"path":'},
                    }]
                },
                "finish_reason": None,
            }]
        }),
        _event({
            "choices": [{
                "delta": {
                    "tool_calls": [{
                        "index": 0,
                        "function": {"arguments": '"note.txt"}'},
                    }]
                },
                "finish_reason": None,
            }]
        }),
        _event({"choices": [{"delta": {}, "finish_reason": "tool_calls"}]}),
        _event({
            "choices": [],
            "usage": {"prompt_tokens": 27, "completion_tokens": 6, "total_tokens": 33},
            "timings": {"prompt_n": 27, "prompt_ms": 9.5, "predicted_n": 6, "predicted_per_second": 42.0},
        }),
        "data: [DONE]",
    ]
    client = LlamaClient(Config(seed=77))
    captured = {}

    def fake_stream(method, url, *, json):
        captured.update({"method": method, "url": url, "payload": json})
        return FakeResponse(events)

    monkeypatch.setattr(client.client, "stream", fake_stream)

    message, meta = client.chat([{"role": "user", "content": "read it"}], [])

    assert message["content"] == "Checking."
    assert message["tool_calls"][0]["id"] == "call-1"
    assert message["tool_calls"][0]["function"]["name"] == "read_file"
    assert message["tool_calls"][0]["function"]["arguments"] == '{"path":"note.txt"}'
    assert captured["method"] == "POST"
    assert captured["url"] == "chat/completions"
    assert captured["payload"]["stream"] is True
    assert captured["payload"]["stream_options"] == {"include_usage": True}
    assert captured["payload"]["seed"] == 77
    assert meta["input_tokens"] == 27
    assert meta["output_tokens"] == 6
    assert meta["total_tokens"] == 33
    assert meta["ttft_ms"] is not None
    assert meta["first_text_ms"] is not None
    assert meta["generation_ms"] is not None
    assert meta["total_latency_ms"] is not None
    assert meta["generation_tokens_per_second"] is not None
    assert meta["prefill_ms"] == 9.5
    assert meta["server_timings"]["predicted_n"] == 6
