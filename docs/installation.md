# Installation

## Requirements

- Apple Silicon Mac, macOS 14+, about 4 GB free RAM, about 2 GB disk for the model.
- [uv](https://docs.astral.sh/uv/) (`brew install uv`). Python 3.11 to 3.13; uv fetches it for you.

## Install

```bash
git clone <this repository> labrador
cd labrador
uv sync --extra mac --extra docs --extra sample
```

Extras are optional dependency groups from `pyproject.toml`:

| Extra | Adds | Needed for |
|---|---|---|
| `mac` | Apple Vision OCR (`ocrmac`), HEIC photos (`pillow-heif`) | Text from images and scanned PDFs on a Mac |
| `docs` | `python-docx` | Indexing `.docx` files |
| `tesseract` | `pytesseract` | OCR on machines without Apple Vision (needs `brew install tesseract`) |
| `sample` | `reportlab`, `matplotlib` | The sample folder and benchmark generators |
| `dev` | `pytest`, `ruff`, `pre-commit`, `reportlab` | Running the tests and linter |

Pass every extra you want in one `uv sync`: syncing with fewer extras uninstalls the rest. To run the tests, add
`--extra dev` (for example `uv run --extra dev pytest -q`).

## First run: the model download

The first command that loads EmbeddingGemma 2 downloads about 1.5 GB from Hugging Face (Apache 2.0). If it asks
for a token, run `hf auth login`. After that the model is cached and nothing leaves your machine.

Check that the model is healthy on your Mac (MPS device, no NaNs, sensible text and image matches):

```bash
uv run python scripts/check_model.py
```

Run it on a new machine, and again after changing `embedder.py`.

## Where indexes live

Each folder gets its own index at `~/.labrador/indexes/<folder>-<hash>/`, holding `index.db` and a `media/`
directory of thumbnails. The directories are `0700` and the files `0600`. Your own folder is only ever read.

Set `LABRADOR_HOME` to move the root (default `~/.labrador`). `labrador index` records the most recent index in
`$LABRADOR_HOME/last_index`, which `search`, `serve` and `stats` use unless you pass `--index DIR`.

## No model? Use the fake backend

`--backend fake` swaps in a hashing embedder that needs no download. It is for testing the plumbing; its results
say nothing about search quality.
