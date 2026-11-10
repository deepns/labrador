# labrador

Local, private, multimodal search over a folder on your Mac, built on
[EmbeddingGemma 2](https://huggingface.co/google/embeddinggemma-2). Describe what you are looking for and it
returns the most relevant **text passages, text read from images, images, PDF pages and pictures embedded in PDFs**.
A learning-sized take on [DigUp](https://github.com/ARahim3/DigUp): Python instead of Swift, ~1,200 lines, every stage visible.

```
folder ──► extractors ──────────────► units ──► EmbeddingGemma 2 ──► SQLite (vectors + FTS5)
            .txt/.md/.html/.docx  → text chunks                       │
            images                → picture + OCR text                 │
            PDF                   → page text, page picture,           │
                                    embedded pictures (+ OCR),         │
                                    OCR for scanned pages              │
query ──► EmbeddingGemma 2 (SearchQuery prompt) ──► cosine, per-modality z-score
                                                   + BM25 keywords ──► RRF ──► group ──► results
```

Docs: see the [documentation front page](docs/README.md).

## Requirements

- Apple Silicon Mac, macOS 14+, ~4 GB free RAM, ~2 GB disk for the model.
- [uv](https://docs.astral.sh/uv/) (`brew install uv`), Python 3.11–3.13 (uv fetches it).
- The model is Apache 2.0; the first run downloads ~1.5 GB from Hugging Face (run `hf auth login` if it asks for a token).

## Quick start

```bash
cd labrador
uv sync --extra mac --extra docs --extra sample     # torch, sentence-transformers, Apple OCR, HEIC, docx

# 1. Is the model healthy on this Mac? (MPS, no NaNs, sane text + image matches)
uv run python scripts/check_model.py

# 2. Try it on a generated sample folder
uv run python scripts/make_sample_folder.py ~/labrador-sample
uv run labrador index ~/labrador-sample
uv run labrador search "are dogs allowed in my apartment"
uv run labrador eval evals/sample_queries.jsonl
uv run labrador serve                               # http://127.0.0.1:8765

# 3. The benchmark: 120-file fictional folder, 114 labelled queries in 13 categories
#    (unzip labrador-bench.zip, or regenerate it: uv run python bench/make_bench.py bench/data)
uv run labrador index bench/data/folder
uv run labrador eval bench/data/queries.jsonl --out evals/out/results.json   # per-category hit@1, hit@5, MRR

# 4. Your own folder
uv run labrador index ~/Documents/whatever
uv run labrador watch ~/Documents/whatever          # keeps the index fresh as files change
```

## Commands

| Command | What it does |
|---|---|
| `labrador index <folder> [--rebuild] [--dim 256] [--image-tokens 560] [--no-ocr]` | First pass, then only new/changed files; removed files drop out |
| `labrador search "<query>" [-k 10] [--only text\|image\|pdf\|visual] [--json]` | Search the last index (or `--index DIR`) |
| `labrador serve [--allow-lan]` | Web UI with thumbnails, filters, open-at-page, Show in Finder. Loopback-only unless you pass `--allow-lan` (which exposes your index to the network) |
| `labrador watch <folder>` | Index, then re-index files 2 s after they stop changing |
| `labrador eval <file.jsonl> [--category X] [--quiet] [--out r.json]` | hit@1, hit@5, MRR@10 overall, per category and for hard negatives |
| `labrador stats` | Files and units by type |

Indexes live in `~/.labrador/indexes/<folder>-<hash>/` (`index.db` + `media/` thumbnails), private to you (directories `0700`, files `0600`). Your folder is only read, never written.
`--backend fake` runs everything with a hashing embedder (no model download) for testing the plumbing.

## Design notes (what to read in the code)

- `embedder.py`: loads the model with `config_kwargs={"audio_config": None}` (skips the 300M audio encoder),
  float32 by default (bfloat16 optional, **never float16**), documents as `title: … | text: …`, queries with
  `prompt_name="SearchQuery"`, images as `{"image": PIL}` with a per-call vision token budget, Matryoshka via `truncate_dim`.
- `extractors.py`: one *unit* = one vector. Units in the same *group* (a photo and its OCR text; a PDF page's
  picture and its text) collapse into one result.
- `search.py`: text→text cosines run higher than text→image cosines (modality gap), so each modality is
  z-scored against itself before ranking; BM25 catches exact strings (a unit must contain every query word,
  so long questions rely on the embeddings); Reciprocal Rank Fusion combines them.
- `store.py`: SQLite + numpy brute force. 100k vectors × 768 dims is ~300 MB and a few ms per query on M-series.

## Tuning knobs

| Knob | Default | Try |
|---|---|---|
| `--dim` | 768 | 512 or 256: ~1–3 points lower quality, 1.5–3× smaller index |
| `--image-tokens` | 280 | 560/1120 for screenshots and detailed photos (slower) |
| `--page-image-tokens` | 560 | 1120 for dense slides/forms; `--no-page-images` to skip page pictures |
| `--dtype bfloat16` | float32 | halves memory; compare results with `check_model.py` first |
| `keyword_weight` (search.py) | 1.0 | lower (0.3–0.7) if exact-word matches crowd out better semantic results; keywords only fire when a unit contains every query word, so this mostly affects short ID/code/name queries |
