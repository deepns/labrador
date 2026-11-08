"""Generation backends for `labrador ask`.

The model runs in a separate process (Ollama by default) and is reached over loopback HTTP only. It gets no tools,
and everything it returns is untrusted text that answer.py checks before showing it.

OpenAICompatLLM - any server speaking OpenAI-style /v1/chat/completions (Ollama, llama.cpp, LM Studio, mlx-lm).
FakeLLM         - scripted, deterministic replies for testing the pipeline without a model or a network.
"""

from __future__ import annotations

import ipaddress
import json
import socket
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from urllib.parse import urlsplit

import httpx

from .config import Settings


class LLMError(RuntimeError):
    """Anything the CLI should print as a one-line error."""


class LLM:
    name = "base"

    def stream(self, messages: list[dict]) -> Iterator[str]: ...
    def complete(self, messages: list[dict], schema: dict | None = None) -> str: ...


def require_loopback(url: str) -> None:
    parts = urlsplit(url)
    host = parts.hostname
    if not host:
        raise LLMError(f"LLM URL has no host: {url!r}")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as e:
        raise LLMError(f"LLM URL has a bad port: {url!r}") from e
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise LLMError(f"Can't resolve LLM host {host!r}: {e}") from e
    # Check the resolved IPs, not the name, so a hostname that points off the machine is caught.
    for info in infos:
        addr = info[4][0].split("%")[0]            # strip an IPv6 %scope
        if not ipaddress.ip_address(addr).is_loopback:
            raise LLMError(f"LLM host {host!r} resolves to {addr}, which is not loopback; your files would leave "
                           "this machine. Use --allow-remote-llm to override.")


@contextmanager
def _http_errors(url: str, timeout: float):
    try:
        yield
    except httpx.ConnectError as e:
        raise LLMError(f"Can't reach the LLM server at {url}. Is it running? (Ollama: `ollama serve`)") from e
    except httpx.TimeoutException as e:
        raise LLMError(f"LLM server at {url} timed out after {timeout:g}s") from e


class OpenAICompatLLM(LLM):
    def __init__(self, url: str, model: str, temperature: float = 0.0, extra: dict | None = None,
                 timeout: float = 120.0, transport: httpx.BaseTransport | None = None):
        self.url, self.model, self.temperature = url, model, temperature
        self.extra, self.timeout, self.name = extra or {}, timeout, model
        # trust_env=False: HTTP(S)_PROXY env vars can never route the prompt off the machine.
        # No redirects: a loopback server can't bounce the request somewhere else.
        self.client = httpx.Client(base_url=url.rstrip("/"), timeout=httpx.Timeout(timeout, connect=5.0),
                                   trust_env=False, follow_redirects=False, transport=transport)

    def _body(self, messages: list[dict], stream: bool) -> dict:
        return {"model": self.model, "messages": messages, "temperature": self.temperature,
                "stream": stream, **self.extra}

    @staticmethod
    def _check(r: httpx.Response) -> None:
        if r.status_code >= 300:
            raise LLMError(f"LLM server returned {r.status_code}: {r.read().decode(errors='replace')[:200]}")

    def stream(self, messages):
        with _http_errors(self.url, self.timeout):
            with self.client.stream("POST", "/chat/completions", json=self._body(messages, True)) as r:
                self._check(r)
                for line in r.iter_lines():
                    if not line.startswith("data:"):       # blank lines and ": keep-alive" comments
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    chunk = json.loads(data)
                    if "error" in chunk:
                        raise LLMError(f"LLM server error: {chunk['error']}")
                    if not chunk.get("choices"):           # e.g. a final usage-only chunk
                        continue
                    delta = chunk["choices"][0]["delta"].get("content")
                    if delta:                              # first chunk has only a role; some send null
                        yield delta

    def complete(self, messages, schema=None):
        body = self._body(messages, False)
        if schema:
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": "answer", "schema": schema, "strict": True}}
        with _http_errors(self.url, self.timeout):
            r = self.client.post("/chat/completions", json=body)
            self._check(r)
            return r.json()["choices"][0]["message"]["content"]

    def models(self) -> list[str]:
        with _http_errors(self.url, self.timeout):
            r = self.client.get("/models")
            self._check(r)
            return [m["id"] for m in r.json()["data"]]


class FakeLLM(LLM):
    """Returns scripted replies in order (repeating the last). Streams in small pieces so tests can split IDs."""

    name = "fake"

    def __init__(self, replies: list[str] | None = None, chunk: int = 3):
        self.replies = replies or ["This is a fake answer [1]."]
        self.chunk = chunk
        self.calls: list[list[dict]] = []

    def _next(self, messages: list[dict]) -> str:
        self.calls.append(messages)
        return self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]

    def stream(self, messages):
        text = self._next(messages)
        for i in range(0, len(text), self.chunk):
            yield text[i:i + self.chunk]

    def complete(self, messages, schema=None):
        return self._next(messages)


def load_llm(s: Settings) -> LLM:
    if s.llm_url == "fake":
        return FakeLLM()
    if s.allow_remote_llm:
        print(f"warning: --allow-remote-llm: your question and file excerpts will be sent to {s.llm_url}",
              file=sys.stderr)
    else:
        require_loopback(s.llm_url)
    return OpenAICompatLLM(s.llm_url, s.llm_model, s.temperature, s.llm_extra)
