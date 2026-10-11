"""Model-server client for the LLM recovery agent.

Two backends, stdlib only (urllib):
  ollama  - Ollama native API. POST /api/chat with stream=false; structured
            output by passing the JSON schema as "format". Health: GET
            /api/version; model presence: GET /api/tags.
  openai  - OpenAI-compatible chat completions, e.g. llama.cpp llama-server
            (docker/ compose service). Structured output via
            response_format json_schema. Health: GET /health.

Configuration comes from the environment so no model name or address is
hard-coded:
  SINGULAROS_LLM_URL      server base URL (default http://127.0.0.1:11434;
                          openai backend: http://127.0.0.1:8080).
                          From inside a QEMU guest with user-mode networking
                          the host is http://10.0.2.2:11434.
  SINGULAROS_LLM_MODEL    model name as listed by `ollama list` (default
                          DEFAULT_MODEL: Qwen3.5 9B, Q4_K_M GGUF from
                          Hugging Face; pull it once with
                          `ollama pull hf.co/unsloth/Qwen3.5-9B-GGUF:Q4_K_M`,
                          5.7 GB). Not sent to the openai backend unless set.
  SINGULAROS_LLM_BACKEND  ollama (default) or openai.
  SINGULAROS_LLM_THINK    true/false: sent as Ollama's "think" option for
                          models that support thinking. Unset: not sent.
  SINGULAROS_LLM_TIMEOUT  request timeout in seconds (default 180).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

BACKENDS = ("ollama", "openai")
DEFAULT_URL = "http://127.0.0.1:11434"
DEFAULT_OPENAI_URL = "http://127.0.0.1:8080"  # docker/ llm service
DEFAULT_MODEL = "hf.co/unsloth/Qwen3.5-9B-GGUF:Q4_K_M"


class LLMError(Exception):
    """The model server could not be reached or returned an unusable reply."""


@dataclass
class LLMConfig:
    base_url: str = DEFAULT_URL
    model: str | None = None
    backend: str = "ollama"
    timeout_s: float = 180.0
    temperature: float = 0.2
    think: bool | None = None

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        think = env.get("SINGULAROS_LLM_THINK")
        backend = env.get("SINGULAROS_LLM_BACKEND", "ollama")
        config = cls(
            base_url=env.get("SINGULAROS_LLM_URL", DEFAULT_URL if backend == "ollama" else DEFAULT_OPENAI_URL),
            model=env.get("SINGULAROS_LLM_MODEL") or (DEFAULT_MODEL if backend == "ollama" else None),
            backend=backend,
            timeout_s=float(env.get("SINGULAROS_LLM_TIMEOUT", "180")),
            think=None if think is None else think.strip().lower() in ("1", "true", "yes"),
        )
        if config.backend not in BACKENDS:
            raise ValueError(f"SINGULAROS_LLM_BACKEND must be one of {BACKENDS}")
        return config


class LLMClient:
    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig.from_env()

    def _url(self, path):
        return self.config.base_url.rstrip("/") + path

    def _request(self, path, payload=None, timeout_s=None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._url(path),
            data=data,
            headers={"Content-Type": "application/json"},
            method="GET" if payload is None else "POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_s or self.config.timeout_s) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:300]
            raise LLMError(f"{path}: HTTP {e.code}: {body}") from e
        except (urllib.error.URLError, OSError) as e:
            raise LLMError(f"{path}: {e}") from e
        except json.JSONDecodeError as e:
            raise LLMError(f"{path}: reply is not JSON: {e}") from e

    def chat(self, messages, schema=None):
        """Send a chat and return the reply text. With a schema, the server
        is asked to constrain the reply to it (structured output)."""
        c = self.config
        if c.backend == "ollama":
            if not c.model:
                raise LLMError("no model configured (set SINGULAROS_LLM_MODEL)")
            payload = {"model": c.model, "messages": messages, "stream": False,
                       "options": {"temperature": c.temperature}}
            if schema is not None:
                payload["format"] = schema
            if c.think is not None:
                payload["think"] = c.think
            reply = self._request("/api/chat", payload)
            try:
                return reply["message"]["content"]
            except (KeyError, TypeError) as e:
                raise LLMError(f"malformed /api/chat reply: missing {e}") from e
        payload = {"messages": messages, "temperature": c.temperature, "max_tokens": 1024}
        if c.model:
            payload["model"] = c.model
        if schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "recovery_proposal", "strict": True, "schema": schema},
            }
        reply = self._request("/v1/chat/completions", payload)
        try:
            return reply["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"malformed chat completion reply: missing {e}") from e

    def health(self):
        """Server status: {"ok", "detail", "model_available"}. Never raises."""
        c = self.config
        try:
            if c.backend == "ollama":
                version = self._request("/api/version", timeout_s=5)["version"]
                # Compare case-insensitively (Hugging Face quant tags are
                # case-insensitive in Ollama); ":latest" may be omitted.
                names = {(m.get("name") or "").lower() for m in self._request("/api/tags", timeout_s=5).get("models", [])}
                names |= {n[:-len(":latest")] for n in names if n.endswith(":latest")}
                available = bool(c.model) and c.model.lower() in names
                detail = f"ollama {version}"
                if not c.model:
                    detail += "; no model configured (set SINGULAROS_LLM_MODEL)"
                elif not available:
                    detail += f"; model {c.model!r} not pulled"
                return {"ok": available, "detail": detail, "model_available": available}
            self._request("/health", timeout_s=5)
            return {"ok": True, "detail": "openai-compatible server healthy", "model_available": None}
        except (LLMError, KeyError, TypeError) as e:
            return {"ok": False, "detail": str(e), "model_available": False}
