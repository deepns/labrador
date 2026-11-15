"""`labrador eval --answers` tests: fake embedder, scripted LLM, no model or network."""

import json

import pytest

from labrador import cli, config
from labrador.llm import FakeLLM, LLMError


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "HOME", tmp_path / "home")
    monkeypatch.setattr(config, "HOME", tmp_path / "home")
    root = tmp_path / "docs"
    root.mkdir()
    (root / "passport.txt").write_text("Passport of Anna Eriksson\nPassport number L898902C3\n")
    cli.main(["index", str(root), "--backend", "fake"])
    rows = [{"question": "passport number", "category": "id", "expect": "passport.txt", "answer": "L898902C3",
             "answerable": True, "bad": ["X999"]},
            {"question": "blood type", "category": "missing", "expect": [], "answer": "", "answerable": False}]
    qa = tmp_path / "qa.jsonl"
    qa.write_text("\n".join(json.dumps(r) for r in rows))
    return root, qa, tmp_path / "out.json", monkeypatch


def run(setup, replies, *extra):
    root, qa, out, mp = setup
    if replies:
        mp.setattr("labrador.llm.load_llm", lambda s: FakeLLM(replies))
    cli.main(["eval", str(qa), "--answers", "--index", str(cli.index_dir_for(root)), "--backend", "fake",
              "--out", str(out), *extra])
    return json.loads(out.read_text())


def test_correct_answer_and_refusal(setup, capsys):
    d = run(setup, ["The number is L898902C3 [1].", "I couldn't find that in your files."])
    a, b = d["results"]
    assert a["em"] and a["cite_hit"] and a["cite_prec"] == 1 and a["hit5"] and not a["false_answer"]
    assert b["refused"] and not b["false_answer"]
    assert d["config"]["model"] and d["summary"]["em"] == 1 and d["summary"]["false_ans"] == 0
    assert "ALL" in capsys.readouterr().out


def test_bad_value_is_false_answer(setup):
    d = run(setup, ["The number is X999 [1].", "I couldn't find that in your files."])
    assert d["results"][0]["false_answer"] and not d["results"][0]["em"]
    assert d["summary"]["false_ans"] == 0.5


def test_answer_to_unanswerable_is_false_answer(setup):
    d = run(setup, ["The number is L898902C3 [1].", "Your blood type is O [1]."], "--category", "missing")
    assert d["summary"]["n"] == 1 and d["results"][0]["false_answer"]


def test_llm_url_fake_end_to_end(setup):
    d = run(setup, None, "--llm-url", "fake", "--quiet")
    assert d["summary"]["n"] == 2 and "by_category" in d


def test_right_value_plus_bad_value_marks_cross(setup, capsys):
    d = run(setup, ["The number is L898902C3, or X999 [1].", "I couldn't find that in your files."])
    assert d["results"][0]["em"] and d["results"][0]["false_answer"]
    assert capsys.readouterr().out.splitlines()[0].lstrip().startswith("✗")


def test_retry_scores_only_second_answer(setup):
    d = run(setup, ["I couldn't find that in your files.", "The number is L898902C3 [1]."], "--category", "id")
    r = d["results"][0]
    assert r["retried"] and r["em"] and "couldn't find" not in r["answer_text"]


class ErrLLM(FakeLLM):
    def stream(self, messages):
        if not self.calls:
            self.calls.append(messages)
            raise LLMError("boom")
        yield from super().stream(messages)


def test_llm_error_recorded_and_run_continues(setup):
    setup[3].setattr("labrador.llm.load_llm", lambda s: ErrLLM(["I couldn't find that in your files."]))
    with pytest.raises(SystemExit) as e:
        run(setup, None)
    assert "1 questions failed" in str(e.value)
    d = json.loads(setup[2].read_text())
    a, b = d["results"]
    assert a["error"] == "boom" and a["false_refusal"] and not a["false_answer"]
    assert b["error"] is None and b["refused"] and d["summary"]["errors"] == 1
