"""Central settings. Override with environment variables or CLI flags."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

MODEL_ID = os.environ.get("LABRADOR_MODEL", "google/embeddinggemma-2")
LLM_URL = os.environ.get("LABRADOR_LLM_URL", "http://127.0.0.1:11434/v1")
LLM_MODEL = os.environ.get("LABRADOR_LLM_MODEL", "gemma4:e4b")   # provisional until the QA benchmark picks one
HOME = Path(os.environ.get("LABRADOR_HOME", Path.home() / ".labrador"))

TEXT_EXT = {".txt", ".md", ".markdown", ".rst", ".csv", ".json", ".yaml", ".yml", ".log",
            ".html", ".htm", ".xml", ".py", ".js", ".ts", ".java", ".go", ".rs", ".c",
            ".cpp", ".h", ".sh", ".sql", ".toml", ".ini"}
DOCX_EXT = {".docx"}
PDF_EXT = {".pdf"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".heic", ".heif"}

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".labrador", ".Trash"}


@dataclass
class Settings:
    model_id: str = MODEL_ID
    backend: str = "gemma"            # "gemma" (real model) or "fake" (plumbing tests, no download)
    device: str = "auto"              # auto -> mps on Apple Silicon, else cpu
    dtype: str = "float32"            # float32 | bfloat16  (never float16: model emits NaNs)
    dim: int = 768                    # Matryoshka: 768 | 512 | 256 | 128
    # Text chunking (characters, not tokens; ~4 chars/token for English)
    chunk_chars: int = 1600
    chunk_overlap: int = 200
    # Vision token budget per image: 70 | 140 | 280 | 560 | 1120 (more = finer detail, slower)
    image_tokens: int = 280
    page_image_tokens: int = 560      # PDF page renders carry small text, so give them more
    # PDF handling
    pdf_page_images: bool = True      # embed each page as a picture (charts, tables, scans)
    pdf_embedded_images: bool = True  # pull out photos/figures inside PDFs
    pdf_max_pages: int = 300
    min_embedded_image_px: int = 120  # skip icons, bullets, logos
    # OCR
    ocr: bool = True
    scanned_page_min_chars: int = 40  # PDF page with less text than this gets OCR'd
    # Files
    max_file_mb: int = 200
    batch_text: int = 16
    batch_image: int = 4
    extra_skip_dirs: set[str] = field(default_factory=set)
    # Local LLM answers (labrador ask)
    llm_url: str = LLM_URL            # OpenAI-compatible base URL; "fake" selects FakeLLM
    llm_model: str = LLM_MODEL        # model name as the runtime knows it
    llm_extra: dict = field(default_factory=lambda: {"keep_alive": "2m"})   # passed to the runtime as-is
    temperature: float = 0.0
    ask_search_k: int = 10            # hits retrieved per question
    ask_sources: int = 5              # hits packed into the prompt
    source_tokens: int = 1500         # cap per source (chars/4)
    context_tokens: int = 4096        # prompt budget; match OLLAMA_CONTEXT_LENGTH
    allow_remote_llm: bool = False    # skip the loopback check (prints a warning)


def index_dir_for(folder: Path) -> Path:
    """One index per folder, kept outside the folder so we never write into it."""
    folder = folder.expanduser().resolve()
    digest = hashlib.sha1(str(folder).encode()).hexdigest()[:10]
    return HOME / "indexes" / f"{folder.name}-{digest}"
