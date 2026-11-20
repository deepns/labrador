"""In-memory timings for one `search` or `ask` request (see docs/design/observability.md).

A Trace is a tree of timed spans. Callers open spans as `with trace.span("retrieve"):` around the code they time,
and `ask()`, `search()` and the LLM backends take `trace=NOOP` so callers that pass nothing record nothing.
Attributes are numbers, booleans or None, never strings, and span names come from SPANS, so no question, path or
model output can reach a trace. Nothing is written to disk; the trace is dropped with the request.
"""

from __future__ import annotations

import time
from contextlib import contextmanager, nullcontext

SPANS = {"attempt", "keywords", "retrieve", "matrix", "lock_wait", "embed_query", "dense", "keyword",
         "collapse", "enrich", "pack", "picture", "generate", "check"}


def _attrs(attrs: dict) -> dict:
    for k, v in attrs.items():
        if v is not None and not isinstance(v, (int, float)):       # bool is an int: allowed; str is not
            raise TypeError(f"trace attribute {k!r} must be a number, bool or None, not {type(v).__name__}")
    return attrs


def _ms(seconds: float) -> float:
    return round(seconds * 1000, 1)


class Trace:
    def __init__(self):
        self.t0 = self.end = time.perf_counter()
        self.root = {"name": "trace", "ms": 0.0, "attrs": {}, "children": []}
        self._stack = [self.root]

    @contextmanager
    def span(self, name: str, **attrs):
        if name not in SPANS:
            raise ValueError(f"unknown span {name!r}")
        node = {"name": name, "ms": 0.0, "attrs": dict(_attrs(attrs)), "children": []}
        self._stack[-1]["children"].append(node)
        self._stack.append(node)
        start = time.perf_counter()
        try:
            yield node
        finally:
            self.end = time.perf_counter()
            node["ms"] = _ms(self.end - start)
            self._stack.pop()

    def set(self, **attrs):
        self._stack[-1]["attrs"].update(_attrs(attrs))

    def walk(self, node=None):
        node = node or self.root
        for c in node["children"]:
            yield c
            yield from self.walk(c)

    def tree(self) -> dict:
        return {**self.root, "ms": _ms(self.end - self.t0)}

    def summary(self) -> dict:
        nodes = list(self.walk())
        def total(*names):
            return round(sum(n["ms"] for n in nodes if n["name"] in names), 1)
        gens = [n for n in nodes if n["name"] == "generate"]
        g = gens[-1]["attrs"] if gens else {}
        ttft, toks = g.get("ttft_ms"), g.get("completion_tokens")
        tok_s = g.get("rt_predicted_per_second")
        if tok_s is None and toks is not None and ttft is not None and gens[-1]["ms"] > ttft:
            tok_s = toks / ((gens[-1]["ms"] - ttft) / 1000)         # decode only: without prefill
        return {"retrieval_ms": total("keywords", "retrieve", "pack"), "answer_ms": total("generate"),
                "total_ms": _ms(self.end - self.t0), "ttft_ms": ttft,
                "prompt_tokens": g.get("prompt_tokens"), "completion_tokens": toks,
                "tok_s": None if tok_s is None else round(tok_s, 1), "cut_off": g.get("cut_off"),
                "attempts": sum(n["name"] == "attempt" for n in nodes) or None}

    def render(self) -> str:
        def lines(n, depth):
            a = " ".join(f"{k}={int(v) if isinstance(v, bool) else v}" for k, v in n["attrs"].items() if v is not None)
            yield f"{'  ' * depth}{n['name']:<{40 - 2 * depth}}{n['ms']:>8.0f} ms  {a}".rstrip()
            for c in n["children"]:
                yield from lines(c, depth + 1)
        return "\n".join(lines(self.tree(), 0))


class _Noop:
    """Same interface as Trace; records nothing."""

    def span(self, name, **attrs):
        return nullcontext()

    def set(self, **attrs):
        pass

    def summary(self) -> dict:
        return {}

    def tree(self) -> dict:
        return {}

    def render(self) -> str:
        return ""


NOOP = _Noop()
