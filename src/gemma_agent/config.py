from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Config:
    base_url: str = os.getenv("LLAMA_BASE_URL", "http://127.0.0.1:8080/v1")
    api_key: str = os.getenv("LLAMA_API_KEY", "no-key")
    model: str = os.getenv("LLAMA_MODEL", "local-model")
    temperature: float = float(os.getenv("LLAMA_TEMPERATURE", "0.2"))
    max_tokens: int = int(os.getenv("LLAMA_MAX_TOKENS", "3584"))
    timeout_seconds: float = float(os.getenv("LLAMA_TIMEOUT", "300"))
    max_steps: int = int(os.getenv("AGENT_MAX_STEPS", "40"))
    seed: int | None = int(os.environ["LLAMA_SEED"]) if os.getenv("LLAMA_SEED") else None
    context_length: int | None = (
        int(os.environ["LLAMA_CONTEXT_LENGTH"])
        if os.getenv("LLAMA_CONTEXT_LENGTH")
        else None
    )
