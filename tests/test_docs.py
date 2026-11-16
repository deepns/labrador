"""Docs checks: relative links and #anchors resolve, documented flags exist, the README command table matches
the CLI, configuration.md names no stale env vars, the quick start runs."""

import re
import shlex
from pathlib import Path
from urllib.parse import unquote

import pytest

from labrador import cli, config

ROOT = Path(__file__).resolve().parent.parent
PAGES = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
LINK_PAGES = [ROOT / "README.md", ROOT / "CLAUDE.md", ROOT / "CHANGELOG.md", *PAGES[1:]]
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


def test_readme_command_table_matches_cli():
    sub = _subparsers()
    table = (ROOT / "README.md").read_text(encoding="utf-8").split("## Commands")[1].split("\n## ")[0]
    documented = set(re.findall(r"^\| `labrador (\w[\w-]*)", table, re.M))
    missing, extra = sorted(set(sub) - documented), sorted(documented - set(sub))
    assert not (missing or extra), f"README Commands table: missing {missing}, extra {extra}"


def test_configuration_page_has_no_stale_env_vars():
    page = (ROOT / "docs" / "reference" / "configuration.md").read_text(encoding="utf-8")
    used = set()
    for src in (ROOT / "labrador").glob("*.py"):
        used |= set(re.findall(r"LABRADOR_[A-Z_]+", src.read_text(encoding="utf-8")))
    stale = sorted(set(re.findall(r"LABRADOR_[A-Z_]+", page)) - used)
    assert not stale, f"docs/reference/configuration.md names env vars no code reads: {stale}"


def _slug(heading):
    return re.sub(r"[^a-z0-9 _-]", "", heading.strip().lower()).replace(" ", "-")


def _scan(path):
    """Return (links as (line, target), heading slugs), ignoring fenced and inline code."""
    links, slugs, fenced = [], set(), False
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced:
            continue
        if m := re.match(r"#{1,6}\s+(.*)", line):
            slugs.add(_slug(re.sub(r"[`*]", "", m.group(1))))
        line = re.sub(r"`[^`]*`", "", line)
        links += [(n, t) for t in re.findall(r"\[[^\]]*\]\(([^)\s]+)", line)]
    return links, slugs


def test_relative_links_resolve():
    scanned, bad = {}, []
    for doc in LINK_PAGES:
        links, slugs = _scan(doc)
        scanned[doc] = slugs
        for n, target in links:
            if re.match(r"(https?:|mailto:)", target):
                continue
            where = f"{doc.relative_to(ROOT)}:{n} -> {target}"
            file, _, anchor = target.partition("#")
            dest = (doc.parent / unquote(file)).resolve() if file else doc
            if not dest.exists():
                bad.append(f"{where} (no such file)")
            elif anchor and dest.suffix == ".md":
                if dest not in scanned:
                    scanned[dest] = _scan(dest)[1]
                if anchor.lower() not in scanned[dest]:
                    bad.append(f"{where} (no such heading)")
    assert not bad, "broken links:\n" + "\n".join(bad)


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
