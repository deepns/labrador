# Searching

Describe what you are looking for in plain words. labrador returns text passages, pictures, PDF pages and text read
from images, ranked together.

```bash
uv run labrador search "are dogs allowed in my apartment"
uv run labrador search "bar chart of quarterly revenue" --only visual -k 5
```

Each result shows its rank, the kind of unit that matched best, the file (and PDF page), the cosine score and which
retrievers found it, then a snippet and, for pictures, the thumbnail's path (paths print in full):

```text
 1. [pdf_ocr      ] ~/labrador-sample/pdfs/scan0007.pdf  p.1   cos=…  via pdf_ocr
      Maple Court Apartments Tenant Notice - Lease Addendum ... Cats and dogs under 40 pounds are permitted ...
      picture: ~/.labrador/indexes/<folder>-<hash>/media/<id>.jpg
```

## Options

| Flag | Default | Effect |
|---|---|---|
| `-k` | 10 | Number of results |
| `--only text` | | Text chunks from text files and `.docx` |
| `--only image` | | Images and the text read from them |
| `--only pdf` | | Anything from a PDF (and pictures inside `.docx`) |
| `--only visual` | | Pictures only: images, PDF page pictures, pictures inside PDFs and `.docx` |
| `--json` | | One JSON array of results, for scripts |
| `--index DIR` | last index | Search a different index |

Stderr gets a count and the time, e.g. `12 results in 0.18 s`; `--json` stdout is unchanged.

## How ranking works

1. Your query is embedded once, with EmbeddingGemma 2's `SearchQuery` prompt.
2. **Meaning.** Every unit gets a cosine score. Text-to-image cosines run lower than text-to-text ones (the
   *modality gap*), so each modality is z-scored against itself; otherwise every picture would rank below
   mediocre text.
3. **Keywords.** SQLite FTS5 (BM25) catches exact strings an embedding can't hold: invoice numbers, error codes,
   names. A unit matches only if it contains every query word, so filler words are dropped first ("what's my
   passport number" becomes "passport number").
4. Reciprocal Rank Fusion merges the two rankings.
5. Units in the same group (a photo and its OCR text, a PDF page's picture and its text) collapse into one result,
   with at most 2 results per file.

If exact-word matches crowd out better semantic results, lower `keyword_weight` in `search.py` (default 1.0; try
0.3–0.7). It mostly affects short ID, code and name queries, since only those match on every word.

The `via` list tells you which units of the group matched. Compare `cos` only between results of the same kind:
because of the modality gap, a picture at 0.30 can be a better match than a passage at 0.55.

## Writing good queries

- Describe the content, not the file: "receipt for the blue armchair" beats "furniture.pdf".
- Exact codes and names work best short: `INV-2024-0117` on its own lets the keyword side match it.
- Long questions still work through meaning, but rarely match on keywords, since every word has to appear.
- Looking for a picture? Add `--only visual` so text doesn't crowd it out.

To get an answer instead of a list, see [Asking questions](asking.md). To measure ranking on your own queries, see
[Evaluating](evaluating.md).
