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

## Local answers (optional)

`labrador ask` needs a local LLM runtime; the embedder never does. Install [Ollama](https://ollama.com), then pull a
4-bit model that fits your RAM:

| RAM | Model | Pull |
|---|---|---|
| 8 GB | Gemma 4 E2B or Qwen3.5-2B | text only |
| 16 GB | Gemma 4 E4B or Qwen3.5-4B (default tier) | `ollama pull gemma4:e4b` |
| 32 GB | Gemma 4 12B or Qwen3.5-9B | better at citing and at conflicts |
| 64 GB | Gemma 4 26B-A4B or 31B | the most accurate |

Pick another model with `--model` (or `LABRADOR_LLM_MODEL`). Before starting Ollama, set:

```bash
export OLLAMA_CONTEXT_LENGTH=4096   # match labrador's --ctx
export OLLAMA_NO_CLOUD=1            # so nothing leaves the machine
```

See [Asking questions](usage/asking.md) for usage and privacy.

## Where indexes live

Each folder gets its own index at `~/.labrador/indexes/<folder>-<hash>/`, holding `index.db` and a `media/`
directory of thumbnails. The directories are `0700` and the files `0600`. Your own folder is only ever read.

Set `LABRADOR_HOME` to move the root (default `~/.labrador`). `labrador index` records the most recent index in
`$LABRADOR_HOME/last_index`, which `search`, `serve` and `stats` use unless you pass `--index DIR`.

## No model? Use the fake backend

`--backend fake` swaps in a hashing embedder that needs no download. It is for testing the plumbing; its results
say nothing about search quality.
