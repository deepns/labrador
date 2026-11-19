"""scripts/ask_bench.py: `run` on a tiny fake index, then `summary` on its output. No model or network."""
import importlib.util
import json
from pathlib import Path

from labrador import cli, config

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("ask_bench", ROOT / "scripts" / "ask_bench.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def test_run_then_summary(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "HOME", tmp_path / "home")
    monkeypatch.setattr(config, "HOME", tmp_path / "home")
    root = tmp_path / "docs"
    root.mkdir()
    (root / "passport.txt").write_text("Passport of Anna Eriksson\nPassport number L898902C3\n")
    cli.main(["index", str(root), "--backend", "fake"])
    qa = tmp_path / "qa.jsonl"
    qa.write_text(json.dumps({"question": "passport number", "expect": "passport.txt", "answer": "L898902C3"}))
    out = tmp_path / "out"
    bench.main(["run", str(qa), "--index", str(cli.index_dir_for(root)), "--tag", "t1", "--llm-url", "fake",
                "--out", str(out)])
    d = json.loads((out / "t1.json").read_text())
    r = d["results"][0]
    assert d["tag"] == "t1" and d["embedder_load_s"] >= 0 and r["timings"]["total_ms"] > 0 and r["tree"]["children"]
    capsys.readouterr()
    bench.main(["summary", str(out)])
    text = capsys.readouterr().out
    assert "t1" in text and "share of wall time" in text
