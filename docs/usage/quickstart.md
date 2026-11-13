# Quick start

Assumes you have followed [Installation](../installation.md). Run everything from the repository root.

Generate a small sample folder, index it, search it:

```bash
uv run python scripts/make_sample_folder.py ~/labrador-sample
uv run labrador index ~/labrador-sample
uv run labrador search "are dogs allowed in my apartment" -k 5
uv run labrador stats
```

`index` embeds every file once and, on later runs, only new or changed files. `search` reads the last index you
built. `stats` shows how many files and units of each type it holds.

Open the web UI (loopback only, so it is reachable just from this machine):

```bash
uv run labrador serve
```

Then browse to <http://127.0.0.1:8765>.

Index your own folder the same way. The folder is only read, never written:

```bash
uv run labrador index ~/Documents/whatever
```

No model download yet? Add `--backend fake` to `index` and `search` to try the plumbing.
