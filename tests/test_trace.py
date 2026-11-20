"""trace.py tests: the recorder itself, plus the spans ask() and the LLM backends put in it."""

import pytest

from labrador.trace import NOOP, Trace


def test_nesting_and_attrs():
    t = Trace()
    with t.span("attempt", n=1):
        with t.span("retrieve"):
            t.set(pool=3, cache_hit=True, x=None)
    tree = t.tree()
    assert [c["name"] for c in tree["children"]] == ["attempt"]
    inner = tree["children"][0]["children"][0]
    assert inner["name"] == "retrieve" and inner["attrs"] == {"pool": 3, "cache_hit": True, "x": None}
    assert "attempt" in t.render() and "pool=3" in t.render()


def test_rejects_strings_and_unknown_names():
    t = Trace()
    with pytest.raises(TypeError):
        with t.span("retrieve", question="my passport"):
            pass
    with pytest.raises(TypeError):
        with t.span("retrieve"):
            t.set(path="/a/b")
    with pytest.raises(ValueError):
        with t.span("nope"):
            pass


def test_noop_records_nothing():
    with NOOP.span("whatever-not-checked", a="b"):
        NOOP.set(a="b")
    assert NOOP.summary() == {} and NOOP.tree() == {} and NOOP.render() == ""


def _gen(t, ttft, toks, ms=1000.0, **attrs):
    with t.span("generate") as node:
        t.set(ttft_ms=ttft, completion_tokens=toks, prompt_tokens=100, cut_off=False, **attrs)
    node["ms"] = ms                                    # pin the duration, which is wall clock otherwise


def test_summary_sums_and_uses_final_attempt():
    t = Trace()
    with t.span("keywords"):
        pass
    for i in (1, 2):
        with t.span("attempt", n=i):
            with t.span("retrieve"):
                pass
            with t.span("pack"):
                pass
            _gen(t, 100.0 * i, 10 * i)
    s = t.summary()
    assert s["attempts"] == 2 and s["ttft_ms"] == 200.0 and s["completion_tokens"] == 20
    assert s["answer_ms"] == 2000.0
    assert s["tok_s"] == 25.0                                          # 20 tokens over (1000 - 200) ms
    assert s["retrieval_ms"] < 50 and s["total_ms"] >= s["retrieval_ms"]


def test_summary_nulls_and_runtime_rate():
    s = Trace().summary()
    assert s["retrieval_ms"] == 0 and s["answer_ms"] == 0 and s["attempts"] is None
    assert s["ttft_ms"] is s["tok_s"] is s["prompt_tokens"] is s["cut_off"] is None
    t = Trace()
    _gen(t, None, 50)                                                  # no ttft (--json): no tok/s
    assert t.summary()["tok_s"] is None and t.summary()["completion_tokens"] == 50
    t = Trace()
    _gen(t, 10.0, 50, rt_predicted_per_second=41.5)                    # the runtime's own rate wins
    assert t.summary()["tok_s"] == 41.5


def test_tok_s_fallback_decodes_from_first_chunk():
    t = Trace()                                        # a thinking model: first chunk at 100 ms, first content at 900 ms
    _gen(t, 900.0, 45, first_chunk_ms=100.0)
    assert t.summary()["tok_s"] == 50.0                # 45 tokens over (1000 - 100) ms, thinking tokens included
    t = Trace()
    _gen(t, 200.0, 40)                                 # no first_chunk_ms (complete()): falls back to ttft
    assert t.summary()["tok_s"] == 50.0
