# Indexing

`labrador index` reads a folder, splits each file into *units* (one vector each), embeds them with EmbeddingGemma 2
and stores them in SQLite. Your folder is only read; everything is written to the index directory.

```bash
uv run labrador index ~/labrador-sample
```

The index goes to `~/.labrador/indexes/<folder>-<hash>/` (`index.db` plus `media/` thumbnails). Set `LABRADOR_HOME`
to move the root, or pass `--index DIR` to choose the directory yourself. `search`, `serve`, `ask`, `eval` and `stats`
use the last index you built unless you pass `--index`.

## What gets indexed

| Files | Units |
|---|---|
| Text, Markdown, HTML, code, CSV, JSON, YAML, logs | Text chunks of about 1,600 characters, overlapping by 200 |
| `.docx` (needs the `docs` extra) | Text chunks, plus pictures embedded in the document |
| Images, including HEIC (needs the `mac` extra) | The picture, plus the text OCR reads from it |
| PDF (first 300 pages) | Page text, a picture of each page, embedded pictures (+ their OCR), OCR for scanned pages |

Units from the same picture or PDF page share a *group*, and a group shows as one search result. labrador skips
hidden files and folders, `.git`, `node_modules`, virtual environments, `.app` bundles and Photos libraries, empty
files and files over 200 MB. The full extension list is in `labrador/config.py`.

OCR uses Apple Vision on a Mac (`mac` extra) or Tesseract elsewhere (`tesseract` extra). `index` prints which
backend it found; without one, images are still indexed as pictures.

## Re-running

Run the same command again and labrador only embeds files whose modification time or size changed. Files you
deleted drop out of the index. A file that fails to extract is recorded with its error and not retried until it
changes; errors are printed and counted in the summary:

```text
{"scanned": 126, "indexed": 3, "removed": 1, "units": 41, "errors": 0, "seconds": 2.1}
```

To start over, delete the index and index everything again:

```bash
uv run labrador index ~/labrador-sample --rebuild
```

## Options

| Flag | Default | Effect |
|---|---|---|
| `--dim` | 768 | Vector size: 512 or 256 cost about 1–3 points of quality for a 1.5–3× smaller index |
| `--image-tokens` | 280 | Vision budget per photo: 560 or 1120 for screenshots and detailed photos (slower) |
| `--page-image-tokens` | 560 | Vision budget per PDF page picture: 1120 for dense slides and forms |
| `--no-page-images` | | Skip PDF page pictures (text only, faster) |
| `--no-ocr` | | Skip OCR on images and scanned pages |
| `--dtype` | float32 | `bfloat16` halves memory; compare with `scripts/check_model.py` first. Never float16 |
| `--device` | auto | `mps` on Apple Silicon, else `cpu` |
| `--backend fake` | | Hashing embedder, no model download: tests the plumbing, says nothing about quality |

An index remembers its model and `--dim`, and refuses a run with a different one. The other options only affect
files embedded from now on, so after changing them re-index with `--rebuild` to keep old and new vectors apart.

## Keeping it fresh

```bash
uv run labrador watch ~/labrador-sample
```

`watch` runs one incremental pass, then re-indexes a file 2 seconds after it stops changing and drops files you
delete. Stop it with Ctrl+C. It takes the same options as `index` except `--rebuild`.

## What's in the index

```bash
uv run labrador stats
```

prints the files and units of each type. To remove an index, delete its directory under `~/.labrador/indexes/`.
