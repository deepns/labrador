"""Embedding backends.

GemmaEmbedder  - EmbeddingGemma 2 via sentence-transformers (MPS on Apple Silicon).
FakeEmbedder   - deterministic hashing embedder for testing the pipeline without the model.

All vectors returned are float32 and L2-normalised, so cosine similarity == dot product.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence

import numpy as np
from PIL import Image

from .config import Settings


def _l2(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    n = np.linalg.norm(x, axis=-1, keepdims=True)
    return x / np.maximum(n, 1e-12)


def format_document(title: str, text: str) -> str:
    """EmbeddingGemma 2 document format. 'none' when there is no real title."""
    title = (title or "none").strip() or "none"
    return f"title: {title} | text: {text}"


class Embedder:
    name = "base"
    dim = 768

    def fingerprint(self) -> str:
        return f"{self.name}:{self.dim}"

    def embed_documents(self, docs: Sequence[tuple[str, str]]) -> np.ndarray: ...
    def embed_images(self, images: Sequence[Image.Image], tokens: int) -> np.ndarray: ...
    def embed_query(self, query: str) -> np.ndarray: ...


class GemmaEmbedder(Embedder):
    def __init__(self, s: Settings):
        import torch
        from sentence_transformers import SentenceTransformer

        device = s.device
        if device == "auto":
            if torch.backends.mps.is_available():
                device = "mps"
            elif torch.cuda.is_available():
                device = "cuda"
            else:
                device = "cpu"
        if s.dtype == "float16":
            raise ValueError("EmbeddingGemma 2 overflows in float16; use float32 or bfloat16.")
        dtype = {"float32": torch.float32, "bfloat16": torch.bfloat16}[s.dtype]

        # We never index audio here, so skip the 300M-param audio encoder (~40% less memory).
        self.model = SentenceTransformer(
            s.model_id,
            device=device,
            model_kwargs={"torch_dtype": dtype},
            config_kwargs={"audio_config": None},
        )
        self.s = s
        self.dim = s.dim
        self.name = s.model_id
        self.device = device

    def _encode(self, inputs, batch_size: int, **kw) -> np.ndarray:
        out = self.model.encode(
            inputs,
            batch_size=batch_size,
            truncate_dim=self.dim if self.dim < 768 else None,
            normalize_embeddings=True,      # re-normalises after Matryoshka truncation
            convert_to_numpy=True,
            show_progress_bar=False,
            **kw,
        )
        out = _l2(out)
        if not np.isfinite(out).all():
            raise RuntimeError("Non-finite embeddings (check dtype: never use float16).")
        return out

    def embed_documents(self, docs):
        if not docs:
            return np.zeros((0, self.dim), np.float32)
        texts = [format_document(t, x) for t, x in docs]
        # prompt="" stops any default prompt being added on top of our manual format.
        return self._encode(texts, self.s.batch_text, prompt="")

    def embed_images(self, images, tokens):
        if not images:
            return np.zeros((0, self.dim), np.float32)
        inputs = [{"image": im} for im in images]
        return self._encode(
            inputs,
            self.s.batch_image,
            processing_kwargs={"image": {"max_soft_tokens": tokens}},
        )

    def embed_query(self, query):
        return self._encode([query], 1, prompt_name="SearchQuery")[0]


class FakeEmbedder(Embedder):
    """Bag-of-words hashing. Only for exercising indexing, storage, search and UI."""

    name = "fake"

    def __init__(self, s: Settings):
        self.dim = s.dim

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, np.float32)
        for w in re.findall(r"[a-z0-9]+", text.lower()):
            h = int(hashlib.md5(w.encode()).hexdigest(), 16)
            v[h % self.dim] += 1.0 if (h >> 64) & 1 else -1.0
        return v

    def embed_documents(self, docs):
        return _l2(np.stack([self._vec(f"{t} {x}") for t, x in docs])) if docs else np.zeros((0, self.dim), np.float32)

    def embed_images(self, images, tokens):
        out = []
        for im in images:
            arr = np.asarray(im.convert("RGB").resize((8, 8)), np.float32).ravel()
            rng = np.random.default_rng(int(arr.sum()) % (2**32))
            out.append(rng.standard_normal(self.dim).astype(np.float32))
        return _l2(np.stack(out)) if out else np.zeros((0, self.dim), np.float32)

    def embed_query(self, query):
        return _l2(self._vec(query))


def load_embedder(s: Settings) -> Embedder:
    return FakeEmbedder(s) if s.backend == "fake" else GemmaEmbedder(s)
