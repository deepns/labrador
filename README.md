# labrador

Local, private, multimodal search over a folder on your Mac, built on
[EmbeddingGemma 2](https://huggingface.co/google/embeddinggemma-2). Describe what you are looking for and it
returns the most relevant **text passages, text read from images, images, PDF pages and pictures embedded in PDFs**.
It can also answer questions from your files with a local LLM (default `qwen3.5:4b`, run by Ollama on your Mac).
A learning-sized take on [DigUp](https://github.com/ARahim3/DigUp): Python instead of Swift, ~2,500 lines, every stage visible.

```
folder ──► extractors ──────────────► units ──► EmbeddingGemma 2 ──► SQLite (vectors + FTS5)
            .txt/.md/.html/.docx  → text chunks                       │
            images                → picture + OCR text                 │
            PDF                   → page text, page picture,           │
                                    embedded pictures (+ OCR),         │
                                    OCR for scanned pages              │
query ──► EmbeddingGemma 2 (SearchQuery prompt) ──► cosine, per-modality z-score
                                                   + BM25 keywords ──► RRF ──► group ──► results
question ──► search ──► top sources ──► local LLM (qwen3.5:4b via Ollama) ──► answer, citations checked
```

## Try it

Apple Silicon Mac, macOS 14+, [uv](https://docs.astral.sh/uv/). The first run downloads the model (~1.5 GB).

```bash
uv sync --extra mac --extra docs --extra sample
uv run python scripts/make_sample_folder.py ~/labrador-sample
uv run labrador index ~/labrador-sample
uv run labrador search "are dogs allowed in my apartment"
uv run labrador serve                               # http://127.0.0.1:8765
```

Your folder is only read, never written. Indexes live in `~/.labrador/indexes/<folder>-<hash>/`, private to you.

## Commands

| Command | What it does | Docs |
|---|---|---|
| `labrador index <folder>` | Index a folder; later runs only embed new or changed files | [Indexing](docs/usage/indexing.md) |
| `labrador watch <folder>` | Index, then re-index files as they change | [Indexing](docs/usage/indexing.md#keeping-it-fresh) |
| `labrador search "<query>"` | Search the last index | [Searching](docs/usage/searching.md) |
| `labrador serve` | Web UI with thumbnails, filters and an Ask mode | [Web UI](docs/usage/web-ui.md) |
| `labrador ask "<question>"` | Answer from your files with a local LLM, cited and checked | [Asking](docs/usage/asking.md) |
| `labrador eval <file.jsonl> [--answers]` | hit@1, hit@5, MRR@10 over labelled queries; with `--answers`, how well `ask` answers | [Evaluating](docs/usage/evaluating.md) |
| `labrador stats` | Files and units by type | [Indexing](docs/usage/indexing.md#whats-in-the-index) |

Every flag is in the [CLI reference](docs/reference/cli.md). Everything else (installation, extras, the FAQ,
security) is on the [documentation front page](docs/README.md).

## Reading the code

Each module's docstring explains its stage of the pipeline:

- `extractors.py`: one *unit* = one vector. Units in the same *group* (a photo and its OCR text; a PDF page's
  picture and its text) collapse into one result.
- `embedder.py`: loads the model without its audio encoder, float32 by default (bfloat16 optional, **never
  float16**), documents as `title: … | text: …`, queries with `prompt_name="SearchQuery"`, Matryoshka via
  `truncate_dim`.
- `search.py`: each modality is z-scored against itself (the modality gap), BM25 catches exact strings, and
  Reciprocal Rank Fusion combines them.
- `store.py`: SQLite + numpy brute force. 100k vectors × 768 dims is ~300 MB and a few ms per query on M-series.
- `indexer.py` and `watch.py`: walk the folder, extract, embed and store, incrementally; `watch` re-indexes files
  a couple of seconds after they stop changing.
- `answer.py` and `llm.py`: retrieve, pack, generate, check and mask for `labrador ask`.
- `trace.py`: in-memory timings for one `search` or `ask` request; nothing is written to disk.
