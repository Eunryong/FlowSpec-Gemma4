from __future__ import annotations

import json
import math
import time
from typing import Any

import httpx

from .config import Config


def _token_count(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        count = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return count if count >= 0 else None


def _timing_ms(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        milliseconds = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return milliseconds if math.isfinite(milliseconds) and milliseconds >= 0 else None


class LlamaClient:
    def __init__(self, config: Config):
        self.config = config
        self.client = httpx.Client(
            base_url=config.base_url.rstrip("/") + "/",
            headers={"Authorization": f"Bearer {config.api_key}"},
            timeout=config.timeout_seconds,
        )

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
        max_tokens = self.config.max_tokens
        if self.config.context_length:
            total_chars = sum(len(str(m.get("content", ""))) for m in messages)
            for m in messages:
                for tc in m.get("tool_calls", []):
                    total_chars += len(str(tc))
            est_prompt_tokens = int(total_chars / 4.2) + 192
            headroom = self.config.context_length - est_prompt_tokens - 128
            if headroom < max_tokens:
                max_tokens = max(1536, headroom)

        payload = {
            "model": self.config.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": self.config.temperature,
            "max_tokens": max_tokens,
            "parallel_tool_calls": False,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if self.config.seed is not None:
            payload["seed"] = self.config.seed
        started = time.perf_counter()
        first_token_at: float | None = None
        first_text_at: float | None = None
        response_id: str | None = None
        finish_reason: str | None = None
        usage: dict[str, Any] = {}
        server_timings: dict[str, Any] = {}
        message: dict[str, Any] = {"role": "assistant", "content": ""}
        tool_calls: dict[int, dict[str, Any]] = {}
        saw_choice = False

        with self.client.stream("POST", "chat/completions", json=payload) as response:
            status_code = getattr(response, "status_code", 200)
            if status_code >= 400:
                body = ""
                if hasattr(response, "read"):
                    try:
                        response.read()
                        body = getattr(response, "text", "") or ""
                    except Exception:
                        pass
                if not body:
                    body = getattr(response, "reason_phrase", "") or ""
                raise RuntimeError(f"llama-server HTTP {status_code}: {body}")
            if hasattr(response, "raise_for_status"):
                response.raise_for_status()
            for line in response.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                chunk_text = line[5:].strip()
                if chunk_text == "[DONE]":
                    break
                try:
                    chunk = json.loads(chunk_text)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(f"Invalid llama.cpp stream event: {chunk_text}") from exc
                if not isinstance(chunk, dict):
                    continue

                response_id = chunk.get("id") or response_id
                if isinstance(chunk.get("usage"), dict):
                    usage = chunk["usage"]
                if isinstance(chunk.get("timings"), dict):
                    server_timings = chunk["timings"]

                for choice in chunk.get("choices") or []:
                    saw_choice = True
                    delta = choice.get("delta") or {}
                    if delta.get("role"):
                        message["role"] = delta["role"]

                    content = delta.get("content")
                    if isinstance(content, str) and content:
                        now = time.perf_counter()
                        if first_token_at is None:
                            first_token_at = now
                        if first_text_at is None:
                            first_text_at = now
                        message["content"] += content

                    hidden_text = delta.get("reasoning_content") or delta.get("refusal")
                    if isinstance(hidden_text, str) and hidden_text and first_token_at is None:
                        first_token_at = time.perf_counter()
                    if isinstance(delta.get("refusal"), str) and delta["refusal"] and first_text_at is None:
                        first_text_at = time.perf_counter()

                    for tool_delta in delta.get("tool_calls") or []:
                        index = tool_delta.get("index")
                        if not isinstance(index, int):
                            index = len(tool_calls)
                        call = tool_calls.setdefault(
                            index,
                            {
                                "id": None,
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            },
                        )
                        if tool_delta.get("id"):
                            call["id"] = tool_delta["id"]
                        if tool_delta.get("type"):
                            call["type"] = tool_delta["type"]
                        function_delta = tool_delta.get("function") or {}
                        generated_function_text = False
                        for field in ("name", "arguments"):
                            fragment = function_delta.get(field)
                            if isinstance(fragment, str) and fragment:
                                call["function"][field] += fragment
                                generated_function_text = True
                        if generated_function_text and first_token_at is None:
                            first_token_at = time.perf_counter()

                    if choice.get("finish_reason") is not None:
                        finish_reason = choice["finish_reason"]

        finished = time.perf_counter()
        if not saw_choice:
            raise RuntimeError("llama.cpp returned no choices")

        if tool_calls:
            message["tool_calls"] = [tool_calls[index] for index in sorted(tool_calls)]
            if not message["content"]:
                message["content"] = None

        prompt_tokens = _token_count(usage.get("prompt_tokens"))
        if prompt_tokens is None:
            prompt_tokens = _token_count(usage.get("input_tokens"))
        if prompt_tokens is None:
            prompt_tokens = _token_count(server_timings.get("prompt_n"))

        completion_tokens = _token_count(usage.get("completion_tokens"))
        if completion_tokens is None:
            completion_tokens = _token_count(usage.get("output_tokens"))
        if completion_tokens is None:
            completion_tokens = _token_count(server_timings.get("predicted_n"))

        total_tokens = _token_count(usage.get("total_tokens"))
        if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
            total_tokens = prompt_tokens + completion_tokens

        usage_source = "usage" if any(
            value is not None
            for value in (
                _token_count(usage.get("prompt_tokens")),
                _token_count(usage.get("completion_tokens")),
            )
        ) else "server_timings" if prompt_tokens is not None or completion_tokens is not None else None

        total_latency_ms = (finished - started) * 1000
        prefill_ms = _timing_ms(server_timings.get("prompt_ms"))
        ttft_ms = (first_token_at - started) * 1000 if first_token_at is not None else None
        first_text_ms = (first_text_at - started) * 1000 if first_text_at is not None else None
        generation_ms = (finished - first_token_at) * 1000 if first_token_at is not None else None
        tokens_per_second = None
        if completion_tokens is not None and generation_ms is not None and generation_ms > 0:
            tokens_per_second = completion_tokens / (generation_ms / 1000)
        if tokens_per_second is not None and not math.isfinite(tokens_per_second):
            tokens_per_second = None

        meta = {
            "elapsed_seconds": total_latency_ms / 1000,
            "total_latency_ms": round(total_latency_ms, 3),
            "ttft_ms": round(ttft_ms, 3) if ttft_ms is not None else None,
            "first_text_ms": round(first_text_ms, 3) if first_text_ms is not None else None,
            "prefill_ms": prefill_ms,
            "generation_ms": round(generation_ms, 3) if generation_ms is not None else None,
            "generation_tokens_per_second": round(tokens_per_second, 3) if tokens_per_second is not None else None,
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "token_source": usage_source,
            "usage": usage,
            "server_timings": server_timings or None,
            "finish_reason": finish_reason,
            "response_id": response_id,
        }
        return message, meta
