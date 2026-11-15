"""docs/reference/cli.md is generated from the argparse parser; keep it in sync with the code."""
import dataclasses
import importlib.util
import re
from pathlib import Path

from labrador import config

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "docs" / "reference" / "cli.md"
spec = importlib.util.spec_from_file_location("gen_cli_reference", ROOT / "scripts" / "gen_cli_reference.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)


def test_cli_reference_is_current():
    assert gen.render() == PAGE.read_text(encoding="utf-8"), (
        "docs/reference/cli.md is stale; regenerate it with: uv run python scripts/gen_cli_reference.py")


def _section(text, cmd):
    return text.split(f"## labrador {cmd}\n")[1].split("\n## ")[0]


def test_shared_llm_flags_render_the_same():
    text = gen.render()
    for flag in ("--model", "--llm-url", "--llm-extra", "--ctx", "--allow-remote-llm"):
        rows = [[ln for ln in _section(text, c).splitlines() if ln.startswith(f"| `{flag}`")] for c in ("ask", "serve")]
        assert len(rows[0]) == 1 and rows[0] == rows[1], flag


def test_render_ignores_terminal_width(monkeypatch):
    monkeypatch.setenv("COLUMNS", "40")
    narrow = gen.render()
    monkeypatch.setenv("COLUMNS", "300")
    assert narrow == gen.render()


def test_configuration_page_covers_settings():
    page = (ROOT / "docs" / "reference" / "configuration.md").read_text(encoding="utf-8")
    names = {f.name for f in dataclasses.fields(config.Settings)}
    for src in (ROOT / "labrador").glob("*.py"):
        names |= set(re.findall(r"LABRADOR_[A-Z_]+", src.read_text(encoding="utf-8")))
    missing = sorted(n for n in names if f"`{n}`" not in page)
    assert not missing, f"docs/reference/configuration.md does not mention: {missing}"
