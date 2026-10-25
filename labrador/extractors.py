"""Turn files into retrievable *units*: text chunks and pictures.

Every unit becomes one vector. A unit also carries a `group` key: units with the same
group are shown as one search result (e.g. a photo and the OCR text read from it, or a
PDF page's picture and its text chunks).
"""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from PIL import Image, ImageOps

from . import ocr
from .config import DOCX_EXT, IMAGE_EXT, PDF_EXT, TEXT_EXT, Settings

try:  # iPhone photos
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

Image.MAX_IMAGE_PIXELS = 200_000_000


@dataclass
class Unit:
    kind: str                 # text | image | image_ocr | pdf_text | pdf_page | pdf_ocr | pdf_image | pdf_image_ocr
    modality: str             # "text" or "image" (which vector space region it came from)
    group: str                # result grouping key within the file
    text: str = ""            # text to embed (text units) or caption shown for image units
    image: Image.Image | None = None
    page: int | None = None   # 1-based PDF page
    chunk: int = 0


def file_type(path: Path) -> str | None:
    ext = path.suffix.lower()
    if ext in PDF_EXT:
        return "pdf"
    if ext in IMAGE_EXT:
        return "image"
    if ext in DOCX_EXT:
        return "docx"
    if ext in TEXT_EXT:
        return "text"
    return None


# ---------------------------------------------------------------- text helpers

def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Paragraph-aware chunking with overlap. Small docs stay one chunk."""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        while len(p) > size:                     # split very long paragraphs on sentences
            cut = p.rfind(". ", 0, size)
            cut = cut + 1 if cut > size // 2 else size
            pieces = p[:cut].strip()
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(pieces)
            p = p[max(cut - overlap, 0):].strip()
        if len(cur) + len(p) + 2 <= size:
            cur = f"{cur}\n\n{p}" if cur else p
        else:
            if cur:
                chunks.append(cur)
            tail = cur[-overlap:] if overlap and cur else ""
            cur = f"{tail}\n\n{p}".strip() if tail else p
    if cur:
        chunks.append(cur)
    return chunks


def _strip_html(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</h\d>|</li>", "\n", raw)
    return html.unescape(re.sub(r"<[^>]+>", " ", raw))


def read_text_file(path: Path, limit: int = 5_000_000) -> str:
    raw = path.read_bytes()[:limit]
    if b"\x00" in raw[:4096]:
        return ""                                 # binary
    text = raw.decode("utf-8", errors="ignore")
    if path.suffix.lower() in {".html", ".htm", ".xml"}:
        text = _strip_html(text)
    return text


def read_docx(path: Path) -> str:
    import docx  # python-docx
    d = docx.Document(str(path))
    parts = [p.text for p in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            parts.append(" | ".join(c.text for c in row.cells))
    return "\n\n".join(p for p in parts if p.strip())


def docx_images(path: Path) -> Iterator[Image.Image]:
    import zipfile
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if name.startswith("word/media/"):
                try:
                    from io import BytesIO
                    yield Image.open(BytesIO(z.read(name))).copy()
                except Exception:
                    continue


# ---------------------------------------------------------------- image helpers

def load_image(path: Path) -> Image.Image:
    im = Image.open(path)
    im = ImageOps.exif_transpose(im)              # respect phone rotation
    return prepare(im)


def prepare(im: Image.Image, max_side: int = 1600) -> Image.Image:
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, "white")
        bg.paste(im, mask=im.split()[-1])
        im = bg
    else:
        im = im.convert("RGB")
    if max(im.size) > max_side:
        im.thumbnail((max_side, max_side))
    return im


def _image_units(im: Image.Image, kind: str, group: str, s: Settings, page=None, chunk=0) -> list[Unit]:
    units = [Unit(kind=kind, modality="image", group=group, image=im, page=page, chunk=chunk)]
    if s.ocr:
        txt = ocr.ocr_image(im)
        if ocr.useful(txt):
            units[0].text = txt[:500]
            units.append(Unit(kind=f"{kind}_ocr", modality="text", group=group, text=txt[: s.chunk_chars * 2],
                              image=None, page=page, chunk=chunk))
    return units


# ---------------------------------------------------------------- per-type extractors

def extract_text(path: Path, s: Settings, docx: bool = False) -> Iterator[Unit]:
    text = read_docx(path) if docx else read_text_file(path)
    for i, c in enumerate(chunk_text(text, s.chunk_chars, s.chunk_overlap)):
        yield Unit(kind="text", modality="text", group=f"c{i}", text=c, chunk=i)
    if docx and s.pdf_embedded_images:
        for j, im in enumerate(docx_images(path)):
            if min(im.size) >= s.min_embedded_image_px:
                yield from _image_units(prepare(im), "pdf_image", f"img{j}", s, chunk=j)


def extract_image(path: Path, s: Settings) -> Iterator[Unit]:
    im = load_image(path)
    if min(im.size) < 32:
        return
    yield from _image_units(im, "image", "img", s)


def extract_pdf(path: Path, s: Settings) -> Iterator[Unit]:
    import pypdfium2 as pdfium
    import pypdfium2.raw as pdfium_c

    pdf = pdfium.PdfDocument(str(path))
    seen_images: set[str] = set()                 # logos repeat on every page; embed once
    try:
        for pno in range(min(len(pdf), s.pdf_max_pages)):
            page = pdf[pno]
            p = pno + 1
            group = f"p{p}"
            tp = page.get_textpage()
            text = tp.get_text_range() or ""
            tp.close()

            render = None
            if s.pdf_page_images or len(text.strip()) < s.scanned_page_min_chars:
                w, h = page.get_size()
                scale = 1400 / max(w, h)
                render = prepare(page.render(scale=scale).to_pil())

            for i, c in enumerate(chunk_text(text, s.chunk_chars, s.chunk_overlap)):
                yield Unit(kind="pdf_text", modality="text", group=group, text=c, page=p, chunk=i)

            if len(text.strip()) < s.scanned_page_min_chars and s.ocr and render is not None:
                txt = ocr.ocr_image(render)
                for i, c in enumerate(chunk_text(txt, s.chunk_chars, s.chunk_overlap)):
                    yield Unit(kind="pdf_ocr", modality="text", group=group, text=c, page=p, chunk=100 + i)

            if s.pdf_page_images and render is not None:
                yield Unit(kind="pdf_page", modality="image", group=group, image=render, page=p,
                           text=text.strip()[:300])

            if s.pdf_embedded_images:
                for j, obj in enumerate(page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE])):
                    try:
                        pw, ph = obj.get_px_size()
                        if min(pw, ph) < s.min_embedded_image_px:
                            continue
                        l, b, r, t = obj.get_bounds()
                        pg_w, pg_h = page.get_size()
                        if (r - l) * (t - b) > 0.8 * pg_w * pg_h:
                            continue              # a full-page scan: the page render already covers it
                        try:
                            im = obj.get_bitmap(render=False).to_pil()
                        except Exception:
                            im = obj.get_bitmap(render=True).to_pil()
                        im = prepare(im)
                        key = hashlib.sha1(im.resize((32, 32)).tobytes()).hexdigest()
                        if key in seen_images:
                            continue
                        seen_images.add(key)
                        yield from _image_units(im, "pdf_image", f"p{p}i{j}", s, page=p, chunk=j)
                    except Exception:
                        continue
            page.close()
    finally:
        pdf.close()


def extract(path: Path, s: Settings) -> Iterator[Unit]:
    t = file_type(path)
    if t == "pdf":
        yield from extract_pdf(path, s)
    elif t == "image":
        yield from extract_image(path, s)
    elif t == "docx":
        yield from extract_text(path, s, docx=True)
    elif t == "text":
        yield from extract_text(path, s)
