# Configuration reference

labrador has no config file. Defaults live in the `Settings` dataclass in `labrador/config.py`; environment variables
change a few of them, and CLI flags (see the [CLI reference](cli.md)) override both for one run.

## Environment variables

| Variable | Default | What it sets |
|---|---|---|
| `LABRADOR_HOME` | `~/.labrador` | Root for indexes and `last_index` (see [Index layout](#index-layout)) |
| `LABRADOR_MODEL` | `google/embeddinggemma-2` | Embedding model ID (`model_id`) |
| `LABRADOR_LLM_URL` | `http://127.0.0.1:11434/v1` | OpenAI-compatible base URL for `ask`, `serve` and `eval --answers` (`llm_url`); `fake` gives a canned answer |
| `LABRADOR_LLM_MODEL` | `qwen3.5:4b` | LLM name as the runtime knows it (`llm_model`); picked by the [answer benchmark](../../evals/answers/REPORT.md) |
| `LABRADOR_DEBUG` | unset | Any value prints a traceback when a file fails to index |

Ollama reads its own variables. Set `OLLAMA_CONTEXT_LENGTH` to the same value as `--ctx` and `OLLAMA_NO_CLOUD=1` so
nothing leaves the machine; see [Installation](../installation.md).

## Settings

Fields of `Settings`, grouped by stage. A flag in the last column sets the field for one run; fields without one
change only in code.

### Embedding

| Field | Default | Flag |
|---|---|---|
| `model_id` | `google/embeddinggemma-2` | `LABRADOR_MODEL` |
| `backend` | `gemma` | `--backend` (`fake` is a hashing embedder for tests, no download) |
| `device` | `auto` (MPS on Apple Silicon, else CPU) | `--device` |
| `dtype` | `float32` | `--dtype` (`float32` or `bfloat16`; never float16, which gives NaNs) |
| `dim` | `768` | `--dim` (Matryoshka: 768, 512, 256, 128) |
| `image_tokens` | `280` | `--image-tokens` (vision budget per image) |
| `page_image_tokens` | `560` | `--page-image-tokens` (PDF page renders carry small text) |
| `batch_text` / `batch_image` | `16` / `4` | |

The index records the model and dim (`meta.embedder`) and refuses a mismatch. After changing `dtype`, a vision budget
or document formatting, re-index with `labrador index --rebuild`.

### Extraction

| Field | Default | Flag |
|---|---|---|
| `chunk_chars` / `chunk_overlap` | `1600` / `200` | characters, about 4 per token in English |
| `pdf_page_images` | `True` | `--no-page-images` turns it off |
| `pdf_embedded_images` | `True` | |
| `pdf_max_pages` | `300` | |
| `min_embedded_image_px` | `120` | skips icons, bullets and logos |
| `ocr` | `True` | `--no-ocr` turns it off |
| `scanned_page_min_chars` | `40` | a PDF page with less text is OCR'd |
| `max_file_mb` | `200` | larger files are skipped |
| `extra_skip_dirs` | empty | added to the built-in skip list (`.git`, `node_modules`, `.venv` and others) |

File types come from the extension sets `TEXT_EXT`, `DOCX_EXT`, `PDF_EXT` and `IMAGE_EXT` in `config.py`.

### Local LLM answers

Used by `labrador ask`, Ask mode in `labrador serve`, and `labrador eval --answers`. All three take the same LLM flags.

| Field | Default | Flag |
|---|---|---|
| `llm_url` | `http://127.0.0.1:11434/v1` | `--llm-url`, `LABRADOR_LLM_URL` |
| `llm_model` | `qwen3.5:4b` | `--model`, `LABRADOR_LLM_MODEL` |
| `llm_extra` | `{"keep_alive": "2m"}` | `--llm-extra` (a JSON object merged over the default) |
| `temperature` | `0.0` | |
| `ask_search_k` | `10` | hits retrieved per question; raised to at least `--k` |
| `ask_sources` | `5` | `--k` on `ask` and `eval --answers` (hits packed into the prompt) |
| `source_tokens` | `1500` | cap per source, counted as characters / 4 |
| `context_tokens` | `4096` | `--ctx`; match `OLLAMA_CONTEXT_LENGTH` |
| `ask_images` | `0` | sources whose original picture is attached; `--images` sets it to 2 |
| `ask_image_px` | `1024` | long side of an attached picture |
| `ask_image_tokens` | `800` | estimated prompt tokens reserved per picture from `context_tokens` |
| `allow_remote_llm` | `False` | `--allow-remote-llm` skips the loopback check and sends file text off-machine |

## Index layout

Each source folder gets one index, kept outside the folder so labrador never writes into it:

```text
$LABRADOR_HOME/                      default ~/.labrador
├── last_index                       the most recent index; commands without a folder use it unless given --index
└── indexes/
    └── <folder>-<hash>/             <hash> = first 10 hex digits of sha1(absolute folder path); mode 0700
        ├── index.db                 SQLite: files, units, vectors, FTS5 table, meta; mode 0600 (also -wal, -shm)
        └── media/                   thumbnails shown in the web UI; mode 0700
```

`meta` holds `embedder` (`name:dim`), `root` (the source folder) and `version` (bumped on every write). Delete the
`<folder>-<hash>` directory to remove an index.
