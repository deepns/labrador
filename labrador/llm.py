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
import time
from collections.abc import Iterator
from contextlib import contextmanager
from urllib.parse import urlsplit

import httpx

from .config import Settings
from .trace import NOOP


class LLMError(RuntimeError):
    """Anything the CLI should print as a one-line error."""


class LLM:
    name = "base"

    def stream(self, messages: list[dict], trace=NOOP) -> Iterator[str]: ...
    def complete(self, messages: list[dict], schema: dict | None = None, trace=NOOP) -> str: ...


def require_loopback(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise LLMError(f"LLM URL must be http or https: {url!r}")
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
        raise LLMError(f"LLM server at {url} timed out after {timeout:g}s. The first question after the model has "
                       "been idle loads it into memory and can take a minute or two; try again.") from e
    except httpx.HTTPError as e:                           # read errors, protocol errors, bad URLs...
        raise LLMError(f"LLM request to {url} failed: {e}") from e
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
        raise LLMError("LLM server sent a response labrador can't parse (is it OpenAI-compatible?)") from e


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _gen_attrs(usage, finish, timings) -> dict:
    """Numbers for the `generate` span from a response's usage, finish_reason and llama.cpp-style timings."""
    usage = usage if isinstance(usage, dict) else {}
    rt = {f"rt_{k}": v for k, v in (timings if isinstance(timings, dict) else {}).items() if k.isidentifier() and _num(v) is not None}
    return {"prompt_tokens": _num(usage.get("prompt_tokens")), "completion_tokens": _num(usage.get("completion_tokens")),
            "cut_off": finish == "length", **rt}


class OpenAICompatLLM(LLM):
    def __init__(self, url: str, model: str, temperature: float = 0.0, extra: dict | None = None,
                 timeout: float = 300.0, deadline: float = 300.0, max_tokens: int | None = 2048,
                 transport: httpx.BaseTransport | None = None):
        self.url, self.model, self.temperature = url, model, temperature
        self.extra, self.timeout, self.name = extra or {}, timeout, model
        self.deadline, self.max_tokens = deadline, max_tokens
        # trust_env=False: HTTP(S)_PROXY env vars can never route the prompt off the machine.
        # No redirects: a loopback server can't bounce the request somewhere else.
        self.client = httpx.Client(base_url=url.rstrip("/"), timeout=httpx.Timeout(timeout, connect=5.0),
                                   trust_env=False, follow_redirects=False, transport=transport)

    def _body(self, messages: list[dict], stream: bool) -> dict:
        cap = {} if self.max_tokens is None else {"max_tokens": self.max_tokens}
        usage = {"stream_options": {"include_usage": True}} if stream else {}    # llm_extra can still override
        return {"model": self.model, "messages": messages, "temperature": self.temperature,
                "stream": stream, **cap, **usage, **self.extra}

    def _over_deadline(self, start: float) -> None:
        # The httpx timeout is per read, so a model that thinks without end never trips it; this caps the total.
        if time.monotonic() - start > self.deadline:
            raise LLMError(f"LLM generation stopped after the {self.deadline:g}s deadline (llm_deadline_s); the "
                           "model may be stuck thinking. Try --llm-extra '{\"reasoning_effort\": \"none\"}' "
                           "or a shorter question.")

    @staticmethod
    def _check(r: httpx.Response) -> None:
        if r.status_code >= 300:
            body = r.read().decode(errors="replace")
            if r.status_code == 501 and "structured output" in body.lower():
                raise LLMError("The LLM runtime doesn't support structured output (Ollama's MLX runner doesn't). "
                               "Drop --json, or use a runtime/model that does, e.g. llama.cpp.")
            raise LLMError(f"LLM server returned {r.status_code}: {body[:200]}")

    def stream(self, messages, trace=NOOP):
        start = time.monotonic()
        with trace.span("generate"), _http_errors(self.url, self.timeout):
            t0 = time.perf_counter()
            first = ttft = finish = usage = timings = None
            n_chunks = 0
            with self.client.stream("POST", "/chat/completions", json=self._body(messages, True)) as r:
                self._check(r)
                trace.set(headers_ms=round((time.perf_counter() - t0) * 1000, 1))
                for line in r.iter_lines():
                    self._over_deadline(start)             # also for keep-alives and reasoning-only chunks
                    if not line.startswith("data:"):       # blank lines and ": keep-alive" comments
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    if "error" in chunk:
                        raise LLMError(f"LLM server error: {chunk['error']}")
                    if first is None:
                        first = round((time.perf_counter() - t0) * 1000, 1)
                    usage = chunk.get("usage") or usage    # the final chunk has usage and empty choices
                    timings = chunk.get("timings") or timings
                    if not chunk.get("choices"):
                        continue
                    finish = chunk["choices"][0].get("finish_reason") or finish
                    delta = chunk["choices"][0].get("delta", {}).get("content")
                    if delta:                              # first chunk has only a role; some send null
                        n_chunks += 1
                        if ttft is None:
                            ttft = round((time.perf_counter() - t0) * 1000, 1)
                        yield delta
            trace.set(first_chunk_ms=first, ttft_ms=ttft, n_chunks=n_chunks, **_gen_attrs(usage, finish, timings))

    def complete(self, messages, schema=None, trace=NOOP):
        body = self._body(messages, False)
        if schema:
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": "answer", "schema": schema, "strict": True}}
        start = time.monotonic()
        with trace.span("generate"), _http_errors(self.url, self.timeout):
            with self.client.stream("POST", "/chat/completions", json=body) as r:
                self._check(r)
                parts = []
                for chunk in r.iter_bytes():
                    parts.append(chunk)
                    self._over_deadline(start)
            reply = json.loads(b"".join(parts))
            choice = reply["choices"][0]
            trace.set(**_gen_attrs(reply.get("usage"), choice.get("finish_reason"), reply.get("timings")))
            return choice["message"]["content"]

    def models(self, timeout: float = 5) -> list[str]:
        with _http_errors(self.url, timeout):
            r = self.client.get("/models", timeout=timeout)
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

    @staticmethod
    def _prompt_tokens(messages: list[dict]) -> int:
        """chars/4 of the message text (pictures count nothing): a stand-in for a runtime's usage."""
        chars = sum(len(p.get("text", "")) if isinstance(p, dict) else len(p)
                    for m in messages for p in (m["content"] if isinstance(m["content"], list) else [m["content"]]))
        return chars // 4

    def stream(self, messages, trace=NOOP):
        text = self._next(messages)
        pieces = [text[i:i + self.chunk] for i in range(0, len(text), self.chunk)]
        with trace.span("generate"):
            yield from pieces
            trace.set(n_chunks=len(pieces), completion_tokens=len(pieces), cut_off=False,
                      prompt_tokens=self._prompt_tokens(messages))

    def complete(self, messages, schema=None, trace=NOOP):
        with trace.span("generate"):
            trace.set(n_chunks=1, completion_tokens=1, cut_off=False, prompt_tokens=self._prompt_tokens(messages))
            return self._next(messages)


def load_llm(s: Settings) -> LLM:
    if s.llm_url == "fake":
        return FakeLLM()
    if s.allow_remote_llm:
        print(f"warning: --allow-remote-llm: your question, file excerpts and any attached pictures will be sent to {s.llm_url}",
              file=sys.stderr)
    else:
        require_loopback(s.llm_url)
    return OpenAICompatLLM(s.llm_url, s.llm_model, s.temperature, s.llm_extra,
                           deadline=s.llm_deadline_s, max_tokens=s.llm_max_tokens)
