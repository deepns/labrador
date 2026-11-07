"""Hybrid multimodal search.

1. Embed the query once (EmbeddingGemma 2 `SearchQuery` prompt).
2. Dense scores: cosine against every unit.
3. Modality calibration. Text-to-text cosines run systematically higher than text-to-image
   cosines (the "modality gap"), so raw cosine would bury every image under mediocre text.
   We z-score each modality against its own distribution for this query, which ranks a
   unit by how much it stands out among its peers.
4. Keyword scores from SQLite FTS5 (BM25) catch exact strings: invoice numbers, error
   codes, names, which no embedding holds exactly. Only units containing every query word
   match, so the keyword side gets the question minus its filler words ("what's my
   passport number" -> "passport number"); the dense side still embeds the whole question.
5. Reciprocal Rank Fusion of the dense and keyword rankings.
6. Collapse units into results (a photo + its OCR text, a PDF page's picture + its text)
   and cap results per file for diversity.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

import numpy as np

from .embedder import Embedder
from .store import Store

RRF_K = 60


@dataclass
class Hit:
    path: str
    file_id: int
    ftype: str
    kind: str              # best-matching unit kind
    page: int | None
    grp: str
    snippet: str
    media: str | None      # thumbnail file name in the index media dir
    media_unit: int | None
    score: float           # fused score (for ordering)
    cosine: float          # best raw cosine in the group
    matched: list[str] = field(default_factory=list)   # which unit kinds matched

    def to_dict(self):
        return asdict(self)


KIND_FILTERS = {
    "text": {"text"},
    "image": {"image", "image_ocr"},
    "pdf": {"pdf_text", "pdf_page", "pdf_ocr", "pdf_image", "pdf_image_ocr"},
    "visual": {"image", "pdf_page", "pdf_image"},
}


# Question and filler words that carry no keyword signal. Store.keyword ANDs every word,
# so one of these in the query is enough to make the keyword side match nothing.
STOPWORDS = set("""
a an the and or but if of to in on at by for with from into about as is are was were be been
being am do does did have has had can could will would should may might must shall
what whats which who whom whose where when why how
i me my mine we us our ours you your yours he him his she her hers it its they them their
this that these those there here any some all
""".split())


def keywords(query: str) -> str:
    """The query with filler words removed, for the keyword (BM25) side of the search."""
    words = re.findall(r"\w+", query.lower())
    return " ".join(w for w in words if len(w) > 1 and w not in STOPWORDS)


def search(store: Store, emb: Embedder, query: str, k: int = 10, only: str | None = None,
           max_per_file: int = 2, keyword_weight: float = 1.0, dense_pool: int = 300,
           keyword_query: str | None = None) -> list[Hit]:
    ids, mods, M = store.matrix()
    if len(ids) == 0:
        return []
    if keyword_query is None:
        keyword_query = keywords(query)
    qv = emb.embed_query(query)
    cos = M @ qv

    z = np.zeros_like(cos)
    gmu, gsd = cos.mean(), cos.std() + 1e-6
    for m in ("text", "image"):
        mask = mods == m
        n = int(mask.sum())
        if n == 0:
            continue
        s = cos[mask]
        mu, sd = (s.mean(), s.std() + 1e-6) if n >= 8 else (gmu, gsd)
        z[mask] = (s - mu) / sd

    order = np.argsort(-z)[:dense_pool]
    fused: dict[int, float] = {}
    for r, i in enumerate(order):
        fused[int(ids[i])] = 1.0 / (RRF_K + r + 1)
    for r, uid in enumerate(store.keyword(keyword_query)):
        fused[uid] = fused.get(uid, 0.0) + keyword_weight / (RRF_K + r + 1)

    cos_by_id = dict(zip(ids.tolist(), cos.tolist()))
    meta = store.units(list(fused))
    allowed = KIND_FILTERS.get(only) if only else None

    groups: dict[tuple, Hit] = {}
    per_file: dict[int, int] = {}
    for uid in sorted(fused, key=fused.get, reverse=True):
        u = meta.get(uid)
        if u is None or (allowed and u["kind"] not in allowed):
            continue
        key = (u["file_id"], u["grp"])
        if key in groups:
            h = groups[key]
            if u["kind"] not in h.matched:
                h.matched.append(u["kind"])
            h.cosine = max(h.cosine, cos_by_id.get(uid, 0.0))
            if not h.snippet and u["text"]:
                h.snippet = u["text"]
            continue
        if per_file.get(u["file_id"], 0) >= max_per_file:
            continue
        per_file[u["file_id"]] = per_file.get(u["file_id"], 0) + 1
        groups[key] = Hit(path=u["path"], file_id=u["file_id"], ftype=u["ftype"], kind=u["kind"],
                          page=u["page"], grp=u["grp"], snippet=u["text"] or "", media=u["media"],
                          media_unit=uid if u["media"] else None, score=fused[uid],
                          cosine=cos_by_id.get(uid, 0.0), matched=[u["kind"]])
        if len(groups) >= k:
            break

    hits = list(groups.values())
    for h in hits:
        sib = store.group_units(h.file_id, h.grp)
        # Image hits: show the text read from the picture (OCR) or the page text, if any.
        if h.kind in ("pdf_page", "image", "pdf_image") or not h.snippet:
            txt = next((s["text"] for s in sib if s["modality"] == "text" and s["text"]), "")
            h.snippet = txt or h.snippet
        # Text hits on a PDF page / picture: attach the page thumbnail.
        if h.media_unit is None:
            m = next((s for s in sib if s["media"]), None)
            if m:
                h.media, h.media_unit = m["media"], m["id"]
    return hits
