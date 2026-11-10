"""Docs checks: relative links resolve, documented flags exist, the quick start runs."""

import re
import shlex
from pathlib import Path
from urllib.parse import unquote

import pytest

from labrador import cli, config

ROOT = Path(__file__).resolve().parent.parent
PAGES = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
FENCE = re.compile(r"```\w*\n(.*?)```", re.S)


def _commands(page):
    """`labrador ...` lines in fenced code blocks, as the tokens after `labrador` (`\\` continuations joined)."""
    for body in FENCE.findall(page.read_text(encoding="utf-8")):
        for line in body.replace("\\\n", " ").splitlines():
            if line.strip().startswith(("labrador ", "uv run labrador ")):
                yield shlex.split(line, comments=True)[line.split().index("labrador") + 1:]


def _subparsers():
    p = cli.build_parser()
    return next(a for a in p._actions if hasattr(a, "_name_parser_map")).choices


@pytest.mark.parametrize("page", PAGES, ids=lambda p: str(p.relative_to(ROOT)))
def test_relative_links_resolve(page):
    text = FENCE.sub("", page.read_text(encoding="utf-8"))
    for target in LINK.findall(text):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        assert (page.parent / unquote(target.split("#")[0])).exists(), f"{page.relative_to(ROOT)}: broken link {target}"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: str(p.relative_to(ROOT)))
def test_documented_flags_exist(page):
    subs = _subparsers()
    for toks in _commands(page):
        if not toks or toks[0] not in subs:
            continue
        known = {o for a in subs[toks[0]]._actions for o in a.option_strings}
        for t in toks[1:]:
            if t.startswith("--"):
                assert t.split("=")[0] in known, f"{page.relative_to(ROOT)}: `labrador {toks[0]}` has no {t}"


def test_quickstart_runs_with_fake_backend(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "HOME", tmp_path / "home")   # cli and config each hold their own HOME
    monkeypatch.setattr(config, "HOME", tmp_path / "home")
    folder = tmp_path / "sample"
    folder.mkdir()
    (folder / "pets.txt").write_text("Dogs are allowed in the apartment with a deposit.")
    ran = 0
    for toks in _commands(ROOT / "docs/usage/quickstart.md"):
        if toks[0] == "serve" or "~/Documents/whatever" in toks:   # serve blocks; the other is a placeholder
            continue
        argv = [str(folder) if t == "~/labrador-sample" else t for t in toks]
        if toks[0] in ("index", "search"):
            argv += ["--backend", "fake"]
        cli.main(argv)
        ran += 1
    assert ran >= 3
    assert "pets.txt" in capsys.readouterr().out
