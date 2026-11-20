"""`labrador ask` CLI tests: fake embedder, FakeLLM or scripted LLMs, no model or network."""

import json

import pytest

from labrador import cli, config
from labrador.llm import FakeLLM

PASSPORT_TXT = "Passport of Anna Eriksson\nPassport number L898902C3\n"


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "HOME", tmp_path / "home")    # cli and config each hold their own HOME
    monkeypatch.setattr(config, "HOME", tmp_path / "home")
    root = tmp_path / "docs"
    root.mkdir()
    (root / "passport.txt").write_text(PASSPORT_TXT)
    cli.main(["index", str(root), "--backend", "fake"])
    return root


def run_ask(capsys, *args):
    capsys.readouterr()
    with pytest.raises(SystemExit) as e:
        cli.main(["ask", *args])
    out = capsys.readouterr()
    code = e.value.code
    if isinstance(code, str):                       # sys.exit("msg") prints msg to stderr and exits 1
        return 1, out.out, out.err + code + "\n"
    return code, out.out, out.err


def use_llm(monkeypatch, llm):
    monkeypatch.setattr("labrador.llm.load_llm", lambda s: llm)


def test_ask_fake_prints_sources_answer_status(folder, capsys):
    code, out, err = run_ask(capsys, "passport number", "--llm-url", "fake")
    assert code == 0
    assert out.index("Sources") < out.index("[1] passport.txt") < out.index("This is a fake answer [1].")
    assert "(note, " in out and "✓ verified against [1] · " in out and "confidence" in out
    assert "--reveal to show" not in out            # nothing was masked


def test_ask_masks_by_default_and_reveals(folder, capsys, monkeypatch):
    use_llm(monkeypatch, FakeLLM(["Your passport number is L898902C3 [1]."]))
    _, out, _ = run_ask(capsys, "passport number")
    assert "L898902C3" not in out and "•••••02C3" in out and "--reveal to show" in out
    _, out, _ = run_ask(capsys, "passport number", "--reveal")
    assert "L898902C3" in out and "--reveal to show" not in out


def test_ask_unverified_status(folder, capsys, monkeypatch):
    use_llm(monkeypatch, FakeLLM(["Your passport number is L898902C4 [1]."]))
    _, out, _ = run_ask(capsys, "passport number", "--reveal")
    assert "✗ unverified: L898902C4" in out and "low confidence" in out


def test_ask_unverified_masked_without_reveal(folder, capsys, monkeypatch):
    use_llm(monkeypatch, FakeLLM(["Your passport number is L898902C4 [1]."]))
    _, out, _ = run_ask(capsys, "passport number")
    assert "L898902C4" not in out and "✗ unverified: •••••02C4" in out and "--reveal to show" in out


def test_ask_json_output_is_masked_json(folder, capsys, monkeypatch):
    import json
    use_llm(monkeypatch, FakeLLM(['{"found": true, "answer": "It is L898902C4", "citations": [1], "quote": null}']))
    code, out, _ = run_ask(capsys, "passport number", "--json")
    d = json.loads(out)
    assert code == 0 and "L898902C4" not in out and "•••••02C4" in d["answer"]
    assert d["sources"][0]["rel_path"] == "passport.txt" and d["retried"] is False
    assert d["check"]["unverified"] == ["•••••02C4"]


@pytest.mark.parametrize("flag", ["-k", "--ctx"])
def test_ask_rejects_non_positive_numbers(folder, capsys, flag):
    code, _, err = run_ask(capsys, "x", flag, "0")
    assert code == 2 and "at least 1" in err and "Traceback" not in err


def test_ask_refusal(folder, capsys, monkeypatch):
    use_llm(monkeypatch, FakeLLM(["I couldn't find that in your files."]))
    code, out, _ = run_ask(capsys, "passport number")
    assert code == 0 and out.rstrip().endswith("refused")


def test_ask_retry(folder, capsys, monkeypatch):
    use_llm(monkeypatch, FakeLLM(["I couldn't find that in your files.", "Passport number L898902C3 [1]."]))
    _, out, _ = run_ask(capsys, "passport number", "--reveal")
    assert "(no answer yet, retrying with “passport”)" in out
    assert out.count("Sources") == 2 and "L898902C3 [1]." in out


def test_ask_remote_url_is_one_line_error(folder, capsys):
    code, out, err = run_ask(capsys, "passport", "--llm-url", "http://example.com/v1")
    assert code == 1 and "Traceback" not in err and err.startswith("error: ") and len(err.splitlines()) == 1


def test_ask_bad_llm_extra(folder, capsys):
    for bad in ("{nope", "[1]"):
        code, _, err = run_ask(capsys, "passport", "--llm-url", "fake", "--llm-extra", bad)
        assert code == 1 and "--llm-extra" in err and "Traceback" not in err


def test_ask_llm_error_exits_1(folder, capsys, monkeypatch):
    class Down(FakeLLM):
        def stream(self, messages, trace=None):
            from labrador.llm import LLMError
            raise LLMError("Can't reach the LLM server")
            yield

    use_llm(monkeypatch, Down())
    code, out, err = run_ask(capsys, "passport number")
    assert code == 1 and "error: Can't reach the LLM server" in err and "verified" not in out


def test_ask_trace_prints_tree_when_llm_fails(folder, capsys, monkeypatch):
    class Down(FakeLLM):
        def stream(self, messages, trace=None):
            from labrador.llm import LLMError
            raise LLMError("Can't reach the LLM server")
            yield

    use_llm(monkeypatch, Down())
    code, out, err = run_ask(capsys, "passport number", "--trace")
    assert code == 1 and "error: Can't reach the LLM server" in err and "attempt" in err and "retrieve" in err


def test_ask_warns_on_cloud_model(folder, capsys, monkeypatch):
    class WithModels(FakeLLM):
        def models(self):
            return ["gemma4:e4b", "gpt-oss:120b-cloud"]

    use_llm(monkeypatch, WithModels())
    code, _, err = run_ask(capsys, "passport number")
    assert code == 0 and "OLLAMA_NO_CLOUD=1" in err


def test_ask_flags_reach_settings(folder, capsys, monkeypatch):
    seen = []
    monkeypatch.setattr("labrador.llm.load_llm", lambda s: seen.append(s) or FakeLLM())
    run_ask(capsys, "passport", "--model", "m", "--ctx", "2048", "-k", "3", "--llm-extra", '{"think": false}',
            "--allow-remote-llm")
    s = seen[0]
    assert (s.llm_model, s.context_tokens, s.ask_sources, s.llm_extra, s.allow_remote_llm) == (
        "m", 2048, 3, {"keep_alive": "2m", "think": False}, True)


def test_ask_json_unsupported_is_one_line_error(folder, capsys, monkeypatch):
    from labrador.llm import LLMError

    class NoSchema(FakeLLM):
        def complete(self, messages, schema=None, trace=None):
            raise LLMError("The LLM runtime doesn't support structured output (Ollama's MLX runner doesn't).")

    use_llm(monkeypatch, NoSchema())
    code, out, err = run_ask(capsys, "passport number", "--json")
    assert code == 1 and len(err.strip().splitlines()) == 1 and "structured output" in err


def test_ask_strips_terminal_escapes(folder, capsys, monkeypatch):
    use_llm(monkeypatch, FakeLLM(["line one\n\x1b]0;pwned\x07 and \x1b[2J [1]"]))
    _, out, _ = run_ask(capsys, "passport number")
    assert "\x1b" not in out and "\x07" not in out and "line one\n" in out


def test_status_line_never_verified_when_shaky():
    c = {"refused": False, "unverified": [], "citations": [1], "bad_citations": [],
         "mrz": "invalid", "confidence": "low"}
    s = cli._status_line(c, False)
    assert "✓" not in s and "[1]" in s and "MRZ check digits INVALID" in s
    assert cli._status_line({**c, "mrz": "", "confidence": "high"}, False).startswith("✓ verified against [1]")


def test_ask_validates_llm_before_loading_embedder(folder, capsys, monkeypatch):
    def boom(s):
        raise AssertionError("embedder loaded")
    monkeypatch.setattr("labrador.embedder.load_embedder", boom)
    code, _, err = run_ask(capsys, "x", "--llm-url", "http://example.com/v1")
    assert code == 1 and err.startswith("error:") and len(err.strip().splitlines()) == 1


def test_ask_images_marks_picture_sources(folder, capsys):
    from PIL import Image
    Image.new("RGB", (64, 64), "white").save(folder / "scan.png")
    cli.main(["index", str(folder), "--backend", "fake"])
    code, out, _ = run_ask(capsys, "passport number", "--llm-url", "fake", "--images")
    assert code == 0 and "scan.png" in out and ", picture)" in out
    assert ", picture" not in run_ask(capsys, "passport number", "--llm-url", "fake")[1]


def test_ask_timings_line_on_stderr(folder, capsys, monkeypatch):
    code, out, err = run_ask(capsys, "passport number", "--llm-url", "fake")
    assert code == 0 and "retrieval " in err and "answer " in err and "\u2192" in err and "tokens" in err
    assert "retrieval" not in out
    assert "first token" not in err and "tok/s" not in err            # null metrics are left out
    assert "cut off" not in err


def test_ask_timings_line_cut_off_warning(folder, capsys, monkeypatch):
    class Cut(FakeLLM):
        def stream(self, messages, trace=None):
            with trace.span("generate"):
                trace.set(cut_off=True, ttft_ms=100.0, completion_tokens=None, prompt_tokens=50)
            yield "Number [1]"

    use_llm(monkeypatch, Cut())
    _, _, err = run_ask(capsys, "passport number")
    assert "the answer was cut off at llm_max_tokens (2048)" in err
    assert "first token 0.1 s" in err and "\u2192" not in err         # the tokens part needs both counts


def test_ask_json_has_timings(folder, capsys, monkeypatch):
    use_llm(monkeypatch, FakeLLM(['{"found": true, "answer": "x", "citations": [1], "quote": ""}']))
    code, out, _ = run_ask(capsys, "passport number", "--json")
    t = json.loads(out)["timings"]
    assert code == 0 and t["attempts"] == 1 and t["answer_ms"] >= 0 and t["ttft_ms"] is None


def test_search_prints_count_on_stderr(folder, capsys):
    capsys.readouterr()
    cli.main(["search", "passport", "--json"])
    out = capsys.readouterr()
    assert isinstance(json.loads(out.out), list) and out.err.strip().endswith(" s") and " in " in out.err
    assert out.err.startswith("1 result in ")


def test_ask_trace_prints_tree_on_stderr(folder, capsys):
    code, out, err = run_ask(capsys, "passport number", "--llm-url", "fake", "--trace")
    assert code == 0 and "retrieve" in err and "generate" in err and "embed_query" in err
    assert "retrieve" not in out and "ms  " not in out                # stdout is still just the answer
    assert "retrieve" not in run_ask(capsys, "passport number", "--llm-url", "fake")[2]


def test_ask_json_trace_only_with_flag(folder, capsys, monkeypatch):
    use_llm(monkeypatch, FakeLLM(['{"found": true, "answer": "x", "citations": [1], "quote": ""}'] * 2))
    t = json.loads(run_ask(capsys, "passport number", "--json", "--trace")[1])["trace"]
    assert t["name"] == "trace" and {c["name"] for c in t["children"]} >= {"keywords", "attempt"}
    assert "trace" not in json.loads(run_ask(capsys, "passport number", "--json")[1])


def test_search_trace_prints_tree_on_stderr(folder, capsys):
    capsys.readouterr()
    cli.main(["search", "passport", "--json", "--trace"])
    out = capsys.readouterr()
    assert isinstance(json.loads(out.out), list)
    assert "matrix" in out.err and "embed_query" in out.err and "collapse" in out.err
    cli.main(["search", "passport"])
    assert "embed_query" not in capsys.readouterr().err
