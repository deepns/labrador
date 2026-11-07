# RAG answer generation over labrador: design of the "answer" step with small local LLMs

Scope note: these notes cover the generation step layered on labrador's existing hybrid search (`labrador/search.py`). Facts about labrador come from reading the repo (README.md, CLAUDE.md, `search.py`, `store.py`, `extractors.py`, `config.py`, `evals/deep/REPORT.md`) and are marked "(repo)". Everything else carries a URL. Research date: 2026-11-02.

### What a labrador search result looks like (repo)
- `search()` returns `Hit` objects: `path`, `file_id`, `ftype`, `kind` (best-matching unit kind: text, image, image_ocr, pdf_text, pdf_page, pdf_ocr, pdf_image, pdf_image_ocr), `page` (1-based PDF page), `grp`, `snippet` (unit text; for image/page hits it is replaced by the group's OCR or page text), `media` (thumbnail file name in the index `media/` dir), `score` (RRF fused), `cosine`, `matched` (unit kinds that matched). Default `k=10`, `max_per_file=2`.
- Text is chunked at `chunk_chars=1600`, overlap 200 (about 400 tokens per chunk), so 5–8 hits fit easily into a 4–8k-token prompt.
- `Store.group_units(file_id, grp)` already returns every unit in a group (picture + OCR text, or a PDF page's picture + text), which is the natural hook for "expand to the group" context packing. The index stores thumbnails only, not full-resolution images; the original file is at `path` in the read-only source folder.
- **Keyword branch uses AND matching** (`Store.keyword`: every query word with length > 1 must be in the unit). The deep eval found this raised MRR from 0.783 to 0.947 on the 114-query benchmark (`evals/deep/REPORT.md`). Consequence for QA: a natural question like "what's my passport number" will almost never fire BM25, because no unit contains "what", "s", "my", "passport" and "number" together. The README says long questions "rely on the embeddings". This bears directly on query handling below.

---

## 1. Query handling: send the question as-is, or rewrite it (HyDE, keywords, multi-query)?

### Takeaway
Send the original question to dense search unchanged, and add one cheap rewrite: an LLM-extracted (or rule-based stopword-stripped) keyword query for the BM25 branch, fused by RRF. HyDE and multi-query are designed for vague or zero-shot queries and add an LLM call before retrieval. For short factual lookups in a personal corpus, the evidence points to rewriting as complementary coverage, not as a replacement.

### Cited Findings
- HyDE has an instruction-following LLM write a hypothetical answer document, embeds it, and retrieves real documents near it. It targets fully zero-shot dense retrieval with no relevance labels. It beats unsupervised Contriever and performs comparably to fine-tuned retrievers across web search, QA and fact verification. — [Gao et al., HyDE, arXiv 2212.10496](https://arxiv.org/abs/2212.10496)
- HyDE's authors acknowledge the generated document may contain false details and rely on the encoder's "dense bottleneck" to filter them out. — [arXiv 2212.10496](https://arxiv.org/abs/2212.10496)
- A 2026 study on complementary query rewriting found that rewriting improves retrieval mainly through complementary coverage rather than standalone gains. Gating rewrites on low top-1 confidence captured about half the gain while rewriting fewer than 40% of queries. That study used BGE dense retrieval plus reranking, not BM25 hybrid. — [Hugging Face Papers 2609.05637](https://huggingface.co/papers/2609.05637) (seen via search snippet only; not fetched in full)
- A TREC RAG system that expanded queries with synonyms and related terms reported keyword expansion improved BM25 nDCG@5 by 24.9% (vocabulary mismatch). — [UTokyo TREC 34 RAG paper](https://trec.nist.gov/pubs/trec34/papers/UTokyo.rag.pdf) (snippet)
- A practitioner write-up (not peer reviewed, 16-question test) found dense-only struggled on a three-word query and hybrid RRF raised precision from 72% to 100%. — [DEV Community](https://dev.to/vivek_vdev/hybrid-retrieval-rrf-how-i-got-100-retrieval-precision-in-a-production-rag-system-1oga)
- Pleias-RAG small models (350M, 1B) are trained to do query routing, query reformulation and source reranking as part of the RAG flow, suggesting reformulation is feasible for very small models. — [Pleias-RAG, arXiv 2504.18225](https://arxiv.org/abs/2504.18225)
- I found no source directly measuring whether rewriting hurts short keyword queries in hybrid BM25+dense. — (search summary; see Gaps)

### Inferences
- In labrador specifically, the AND-matching BM25 branch is effectively off for natural-language questions (repo). The biggest, cheapest win is to give BM25 a keyword version of the question: "what's my passport number?" becomes "passport number", or just "passport". This can be done without an LLM (a stopword list plus question words such as what/where/when/my/is/the), which keeps it testable with the fake embedder. An LLM keyword extractor is an optional upgrade.
- Recommended default: `dense(original question)` + `bm25(keywords)`, fused with the existing RRF. Optional: if the top result's fused score or z-score is weak, also run `dense(keywords)` and fuse. This mirrors the "gate rewrites on low confidence" finding.
- An AND query over several keywords can still miss. A fallback ladder (all keywords AND, then the most specific single keyword such as the longest noun or a rare term) is a cheap, readable heuristic. It should be checked with `labrador eval` because the deep eval showed OR matching hurt ranking.
- HyDE is a poor fit for ID lookups: the hypothetical document would invent a passport number, and the embedding of an invented number carries no signal. The question as-is ("passport number") already embeds close to a passport scan's OCR text. Treat HyDE as an experiment for vague questions ("what did we decide about hiring"), not a default.
- EmbeddingGemma's `SearchQuery` prompt is already tuned for questions as queries (repo `embedder.py`), which weakens the case for rewriting the dense side.

### Gaps
- No controlled ablation found of raw vs keyword-rewritten vs HyDE queries on a hybrid BM25+dense personal-document corpus. labrador's benchmark (`bench/data/queries.jsonl`) is the right place to run one: raw question, stopword-stripped keywords, LLM keywords, and HyDE, scored by hit@1/MRR.

---

## 2. Top-k and context packing: chunk vs page vs group expansion, token budget, ordering, metadata

### Takeaway
Pack the top ~5 (up to 8) collapsed results, expanding each to its full group (all text units of that photo or PDF page), under a fixed token budget of about 3–6k tokens for a 4–8B model. Put documents first and the question last, number each source and wrap it in tags with file name, path, page and modification date. Order by relevance with the best hit first; with only 5 short sources, lost-in-the-middle effects are small.

### Cited Findings
- "Lost in the Middle": performance is highest when relevant information is at the beginning or end of the context and drops significantly in the middle (U-shaped curve). It also decreases as the input context grows, even for explicitly long-context models. Tasks were multi-document QA and key-value retrieval. — [Liu et al., arXiv 2307.03172 / TACL 2024](https://arxiv.org/abs/2307.03172)
- Anthropic's long-context guidance: put long documents near the top of the prompt, above the query and instructions. "Queries at the end can improve response quality by up to 30 percent in tests, especially with complex, multidocument inputs." — [Claude prompting best practices, long context prompting](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)
- Same source: wrap each document in `<document>` tags with `<document_content>` and `<source>` (and other metadata) subtags. — [Claude prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)
- Anthropic's Contextual Retrieval work (as reported by secondary sources) passed about 150 retrieved candidates to a reranker and gave the top 20 chunks to the model. Top-20 retrieval failure fell from 5.7% (embeddings baseline) to 1.9% with contextual embeddings + contextual BM25 + reranking, a 67% reduction. A critic notes top-20 is an unusually large cutoff for many applications. — [Gradient Flow summary](https://gradientflow.com/contextual-retrieval-rag/); [critique, Medium/Almond AI](https://medium.com/almond-ai/responding-to-anthropics-contextual-retrieval-for-rag-apps-why-context-is-not-all-you-need-af503985aa55)
- LlamaIndex's default response synthesis mode is `compact`: pack as many retrieved chunks as fit into each prompt and refine across prompts only if they overflow. Other modes: `refine` (one LLM call per chunk), `tree_summarize`, `simple_summarize` (truncate to one prompt), `accumulate`. — [LlamaIndex response synthesizers](https://developers.llamaindex.ai/python/framework/module_guides/querying/response_synthesizers/)

### Inferences
- labrador's units are small (about 400-token chunks, one PDF page, one photo's OCR), and personal-document questions are usually single-hop. A single-prompt "stuff/compact" approach is right; refine or tree-summarize add LLM calls for no gain on lookups.
- Group expansion is the natural unit of context: `search()` already collapses by group, and `Store.group_units` returns the siblings. For a PDF text hit, include the full page text (all chunks of that page in chunk order). For an image hit, include its OCR text. Neighbour expansion across chunks (chunk n±1 in long text files) is useful for long notes but optional.
- Budget suggestion: about 4k tokens of context for a 4B model, 6–8k for 8–14B. Approximate tokens as chars/4, which `config.py` already assumes. Truncate each source to a per-source cap (for example 1,500 tokens) so one long page cannot crowd out the others.
- Ordering: with 5 sources totalling a few thousand tokens, lost-in-the-middle matters less than in the paper's 20–30 document setting. Keeping rank order (best first) is simplest and readable. A "best first and last" sandwich is a possible later tweak, unmeasured here.
- Metadata per source should include `[n]`, file name, relative path, page, kind (text, OCR from photo, PDF page), and file modification date. Dates help "latest" questions such as "which passport is current?". The `files` table has `mtime` (repo `store.py`).
- k: retrieve with labrador's k=10 (already collapsed, max 2 per file), then pass the top 5 to the LLM. The deep eval's hit@5 of 1.00 on the benchmark (repo REPORT.md) suggests 5 is enough on that corpus.

### Gaps
- No source found that measures the optimal k specifically for small (4–14B) local models on short personal documents. Run it as an experiment (k = 3/5/8 on answer accuracy).
- No source found quantifying lost-in-the-middle for current small models (Qwen3, Gemma 3) at short (<8k) contexts.

---

## 3. Reranking: is a cross-encoder or LLM rerank worth it at this scale?

### Takeaway
Probably not as a first step. labrador's retrieval already reaches hit@5 = 1.00 and MRR 0.947 on its benchmark, and the generator reads all top-5 anyway, so reranking mainly fixes order within the window. Add a reranker only if answer evals show the right source missing from the top 5. If one is added, Qwen3-Reranker-0.6B (Apache 2.0, 32K context) is the strongest small open option found, but it is text-only.

### Cited Findings
- Qwen3-Reranker comes in 0.6B, 4B and 8B, Apache 2.0, 32K context, instruction-aware. MTEB-R: 0.6B 65.80, 4B 69.76, 8B 69.02, vs BGE-reranker-v2-m3 (0.6B) 57.03, gte-multilingual-reranker-base 59.51, jina-multilingual-reranker-v2-base 58.22. Scores were measured reranking the top-100 from Qwen3-Embedding-0.6B. — [Qwen3-Reranker-0.6B model card](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B)
- Qwen3-Reranker scores relevance as P("yes") from yes/no logits, using an `<Instruct>/<Query>/<Document>` template. Custom English instructions typically improve results by about 1–5%. It runs via Transformers or Sentence Transformers (`predict()`, sigmoid for 0–1). — [model card](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B)
- In Anthropic's Contextual Retrieval experiments (secondary reporting), adding a reranker on top of contextual embeddings + BM25 cut top-20 failure from 2.9% to 1.9%. — [Gradient Flow](https://gradientflow.com/contextual-retrieval-rag/)
- labrador benchmark (repo `evals/deep/REPORT.md`): hit@1 0.90, hit@5 1.00, MRR@10 0.947 with AND keyword matching, on 120 files and 114 queries.

### Inferences
- At labrador's scale (hundreds to tens of thousands of units), latency is not the issue: a 0.6B reranker over 20–30 candidates is cheap on Apple Silicon. The real costs are another 1.2 GB model download and code complexity in a "learning-sized" tool.
- A text-only reranker would see only OCR/page text for image hits, which reintroduces the modality problem labrador solved with per-modality z-scores. Image-only hits with no OCR text cannot be reranked this way. Rerank only text-bearing groups, or skip reranking.
- The generator LLM itself acts as an implicit reranker when it reads 5 sources and cites the relevant one. That is the cheapest "LLM rerank".

### Gaps
- No independent benchmark found of rerankers on personal/OCR'd document collections.
- Aggregator scores for Qwen3-Reranker were inconsistent ([BenchmarkList](https://benchmarklist.com/providers/reranker/), [Superlinked](https://www.superlinked.com/models/qwen-qwen3-reranker-0-6b.md)); only the model-card numbers above are reliable.

---

## 4. Multimodal results: OCR text, the image to a VLM, or both?

### Takeaway
Default to OCR text (cheap, works with any text LLM), and offer a VLM path that sends the original image (from `path`, not the thumbnail) alongside its OCR text when the top hit is an image or scanned page. For IDs and passports, prefer "both" and treat numbers as unverified unless OCR and the image agree, or a checksum validates (MRZ check digits).

### Cited Findings
- Generic OCR does not transfer well to MRZ: a 2026 master's thesis reports 96.4% full-MRZ accuracy on its own 1,873 smartphone captures with an MRZ-specific pipeline, dropping to about 70% on MIDV datasets. It concludes "generic OCR does not transfer; MRZ is a domain-specific OCR problem." — [Eberdorfer thesis poster, FH Technikum Wien](https://media-hp.technikum-wien.at/media/20260616094052/Master_Thesis_Eberdorfer_Poster_A0.pdf)
- A dedicated CNN MRZ pipeline reached 100% MRZ detection and 99.25% character-recognition macro-F1 on a passport/visa dataset; earlier general OCR methods were reported to fail on MRZ from digital passport images. — [IJDAR, arXiv 2009.05489](https://ar5iv.labs.arxiv.org/html/2009.05489)
- The MRZ (ICAO TD3 layout) is self-verifying via check digits, and cross-checking the MRZ against the visual zone catches errors. — [Eberdorfer poster](https://media-hp.technikum-wien.at/media/20260616094052/Master_Thesis_Eberdorfer_Poster_A0.pdf); [Didit blog (vendor)](https://didit.me/blog/ocr-reliability-mrz-parsing/)
- Small VLMs are strong at document reading: Qwen3-VL-4B-Instruct about 95.3 DocVQA / 88.1% OCRBench, Qwen3-VL-8B about 96.1 / 89.6% (aggregator figures). An independent paper reports Qwen3-VL-4B at 94.9 DocVQA and 873 OCRBench. — [llm-stats](https://llm-stats.com/models/compare/qwen3-vl-4b-instruct-vs-qwen3-vl-8b-instruct); [Qianfan-OCR, arXiv 2603.13398](https://arxiv.org/pdf/2603.13398)
- No published accuracy numbers were found for VLMs on MRZ parsing specifically. — (search summary)

### Inferences
- labrador already runs Apple Vision OCR, and image hits already carry OCR text in `snippet` (repo). Passing that text is the zero-cost default and works with any text-only model.
- For a passport photo, the passport number appears twice: in the visual zone and in MRZ line 2 (characters 1–9, followed by a check digit). A tiny deterministic validator (ICAO 7-3-1 weighting) in `answer.py` could flag or confirm a number the LLM extracted from OCR text. It is readable, about 15 lines, and directly targets the "garbled digits" risk. This is an inference; the check-digit scheme itself is standard ICAO 9303.
- VLM path: thumbnails in `media/` are downscaled, so send the original file (read-only source folder, path in the hit) resized to the VLM's input budget. Send OCR text too: the VLM can use it as a hint and the prompt can ask it to report disagreement.
- Model choice: a single VLM (for example Qwen3-VL-8B or Gemma 3 12B via Ollama or MLX-VLM) can serve as both text answerer and image reader, avoiding two models. Gating "attach image" on `hit.kind in {image, image_ocr, pdf_page, pdf_ocr, pdf_image...}` and only for the top 1–2 hits keeps prompts small.

### Gaps
- No head-to-head of Apple Vision OCR vs a small VLM on passports, driver's licences or receipts. labrador would need its own small labelled set (fictional documents, as in `bench/`) to measure it.
- I did not verify the Qwen3-VL numbers against the official Qwen technical report.

---

## 5. Prompting for grounded answers: system prompt, citations, "not found", hallucinated numbers, structured output

### Takeaway
Use a short system prompt that (a) answers only from numbered sources, (b) cites `[n]` after each claim, (c) copies numbers and IDs character-for-character from the source, and (d) says a fixed sentence such as "I couldn't find that in your files." when no source contains the answer. Back the prompt with code-side checks: verify that every cited `[n]` exists and that any number or ID in the answer appears verbatim in a cited source. Prompting alone handles missing evidence reasonably but fails on misleading evidence.

### Cited Findings
- Anthropic recommends asking the model to quote relevant parts of the documents first, then answer ("ground responses in quotes"), to focus on relevant content. — [Claude prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)
- Anthropic's Citations API (launched January 2025) grounds answers in user-provided documents and points claims back to them. A 2025 paper notes its chunking was undocumented and citation span size varied from a phrase to a paragraph. — [Convergence India](https://convergenceindia.org/industry-news/artificial-intelligence/anthropics-citations-this-new-feature-will-make-sure-you-get-relevant-and-accurate-responses-from-ai-every-time-check-out-how-119003); [Pleias-RAG, arXiv 2504.18225](https://arxiv.org/abs/2504.18225)
- Pleias-RAG (350M, 1B) natively supports citation with literal quotes, and its authors say the models are competitive with Qwen-2.5-7B, Llama-3.1-8B and Gemma-3-4B on HotPotQA/2wiki. This is evidence that small models can be made to quote sources. — [arXiv 2504.18225](https://arxiv.org/abs/2504.18225)
- GRAB-RAG (2026) tested small frozen RAG models (3.8B–8B) under supportive, degraded, missing and misleading contexts. Models abstain reliably when evidence is missing, but under explicit abstention prompting still answer 41.6% of misleading questions, and 63% of those repeat the planted wrong entity verbatim. Chain-of-thought adds little. A generator-side conflict check cut the misleading-answer rate to 13.3% but discarded many correct answers. — [Setiawan, "Prompt-Based Abstention Fails Under Misleading Context", alphaXiv 2608.22228](https://alphaxiv.org/abs/2608.22228v1)
- AbstentionBench (Meta FAIR, NeurIPS 2025): across 20 datasets, abstention is unsolved, scaling helps little, and reasoning fine-tuning degrades abstention by 24% on average. This is not RAG-specific. — [arXiv 2506.09038](https://arxiv.org/abs/2506.09038v1)
- LIT-RAGBench reports some models over-abstain on insufficient-evidence tasks even when a valid answer is possible, so a high abstention rate is not automatically good. — [arXiv 2603.06198](https://arxiv.org/pdf/2603.06198)
- Ollama supports structured outputs by passing a JSON schema (dict or Pydantic `model_json_schema()`) in the `format` parameter of `/api/chat`, available since December 2024. Passing `format="json"` gives unconstrained JSON only. Low temperature (such as 0) is recommended for schema adherence, and outputs should still be validated. — [Ollama blog: Structured outputs](https://registry.ollama.ai/blog/structured-outputs); [glukhov.org guide](https://www.glukhov.org/post/2025/09/llm-structured-output-with-ollama-in-python-and-go/)

### Inferences
- Draft system prompt (small-model friendly: short, imperative, one example):
  - "You answer questions about the user's own files using only the numbered sources below. Cite the source after each fact like [2]. Copy numbers, IDs, dates and names exactly as written in the source; never complete or correct them. If the sources do not contain the answer, reply exactly: I couldn't find that in your files. If sources disagree, say so and cite both."
  - Then `<sources>` with `<source id="1" file="passport_scan.jpg" path="docs/ids/passport_scan.jpg" page="" kind="photo OCR" modified="2024-03-02">…</source>`, then the question last.
- Free text with `[n]` markers streams well and is readable. JSON schema (`{"answer": str, "citations": [int], "quote": str, "found": bool}`) is more robust for evaluation and for the web UI, but constrained decoding hides tokens until the object closes, which hurts streaming. A pragmatic split: the CLI/web stream plain text with `[n]`, and `ask --json` / eval use the schema.
- Code-side guards are the readable, deterministic complement to prompting, given GRAB-RAG's evidence that prompts do not stop wrong answers under misleading context:
  1. Parse `[n]`; drop or flag citations outside 1..N.
  2. Extract digit/ID-like tokens (regex `[A-Z0-9]{6,}` and dates) from the answer; require each to appear verbatim (after whitespace normalisation) in a cited source. If not, mark the answer "unverified" rather than silently showing it.
  3. Optionally require a verbatim `quote` field and check it is a substring of the cited source. This catches fabricated quotes cheaply.
- A "confidence" field self-reported by a 4–8B model is not reliable evidence (AbstentionBench shows calibration problems even at scale). Derive confidence from signals instead: retrieval score of the cited hit, whether the number passes the verbatim check, and the MRZ checksum when applicable.
- For personal data, a misleading context often means an expired passport and a current one both in the folder. The "if sources disagree, say so and cite both" instruction plus file modification dates in metadata directly target that case.

### Gaps
- GRAB-RAG's abstract page does not name the three models tested. Details were not verified beyond the abstract page.
- No source found comparing citation accuracy of current 4–30B general models (Qwen3, Gemma 3, Llama) with `[n]` prompting specifically.

---

## 6. Agentic / iterative retrieval vs single-shot

### Takeaway
Single-shot (one retrieval, one generation) is right for a learning-sized tool and for single-fact personal lookups. At most, add one deterministic retry: if the first pass returns "not found" or retrieval scores are weak, re-search with the keyword-only query and answer once more. This is a fixed two-step pipeline, not an LLM-driven loop.

### Cited Findings
- Adaptive-RAG routes each query by predicted complexity among no retrieval, single-step and multi-step retrieval, using a small classifier. It reports F1 46.94 with 2.17 average steps vs 4.69 steps for always-multi-step (FLAN-T5-XL). It compares against Self-RAG as a baseline. — [Adaptive-RAG, arXiv 2403.14403](https://arxiv.org/pdf/2403.14403)
- Self-RAG makes retrieval decisions during generation via reflection tokens, requiring a specially trained model, while Adaptive-RAG decides up front. — [AlphaXiv overview of Adaptive-RAG](https://alphaxiv.org/overview/2403.14403v2); [Self-RAG, arXiv 2310.11511](https://arxiv.org/abs/2310.11511)
- Practitioner estimates put iterative agentic RAG at roughly 2.5x to 3.5x the token cost of classic RAG. Figures are inconsistent across secondary sources, and uncapped loops can burn large costs on a single stuck query. — [DEV Community](https://dev.to/mr_manushukla/agentic-rag-costs-25x-classic-rag-the-2026-routing-decision-14l6); [ecorpit](https://ecorpit.com/agentic-rag-vs-classic-rag-adaptive-routing-cost-2026/)
- Pleias-RAG's authors build routing and reformulation into small models, but with dedicated training. — [arXiv 2504.18225](https://arxiv.org/abs/2504.18225)

### Inferences
- Locally, "cost" means latency: each extra LLM round on a 8B model on an M-series Mac adds seconds of prefill plus generation. A tool loop with a 4–8B model also adds failure modes (malformed tool calls, loops), which would obscure the pipeline the project is meant to show.
- Most personal-document questions ("passport number", "wifi password", "when does my lease end") are single-hop, which is exactly the class where Adaptive-RAG chooses single-step retrieval.
- A readable middle ground: `answer()` = search → pack → generate; if the result is "not found" and the keyword fallback was not yet tried, run search once more with keywords and regenerate. Cap at two passes.

### Gaps
- No measured comparison found of agentic vs single-shot RAG with 4–30B local models on personal-document QA.

---

## 7. Streaming answers to CLI and web

### Takeaway
Stream tokens from the local server (Ollama's native `/api/chat` with `stream: true`, or any OpenAI-compatible `/v1/chat/completions` with `stream=True`). Print sources first (they are known before generation), then stream the answer. In the web UI, use an SSE or chunked endpoint and render `[n]` markers as links to the already-shown result cards.

### Cited Findings
- Ollama exposes an OpenAI-compatible `/v1` endpoint. The OpenAI Python client works with `base_url` set to it and any placeholder API key, and streaming uses `stream=True` on `chat.completions.create`, emitted as OpenAI-style SSE chunks. `stream_options={"include_usage": true}` appends token usage to the final chunk. — [tkmxai guide](https://www.tkmxai.it.com/running-ollama-with-the-openai-compatible-api-for-local-and-hybrid-inference-wor) (third-party)
- Ollama's native `/api/chat` streams token by token as newline-delimited JSON, which can be read with `requests` and manual line parsing. — [eastondev tutorial](https://eastondev.com/blog/es/posts/ai/ollama-api-calls/) (third-party)
- Ollama processes requests sequentially per model by default, so streaming slows under concurrent load. — [tkmxai guide](https://www.tkmxai.it.com/running-ollama-with-the-openai-compatible-api-for-local-and-hybrid-inference-wor) (third-party)
- JSON-schema structured output is via `format` on `/api/chat`. — [Ollama blog](https://registry.ollama.ai/blog/structured-outputs)

### Inferences
- Targeting the OpenAI-compatible chat API (a plain `httpx`/`requests` POST, no SDK) lets labrador work with Ollama, LM Studio, llama.cpp `llama-server` and `mlx_lm.server` without backend-specific code, and keeps dependencies minimal. Make `--llm-url` and `--model` the only configuration.
- Mirror the existing `--backend fake` pattern: a fake LLM that echoes the top source's first sentence with `[1]` would let `pytest` cover `answer.py` plumbing (packing, citation parsing, verbatim-number check) without any model.
- Constrained JSON and token streaming conflict. Stream text for humans and use JSON for `--json` and eval.

### Gaps
- I did not fetch Ollama's official API reference; the endpoint details above come from the official structured-outputs blog and third-party guides. Verify against docs.ollama.com before implementing.

---

## 8. Evaluating answer quality

### Takeaway
Extend `bench/data/queries.jsonl` with QA rows (`question`, `expect` file stem, `answer` gold string or regex, `answerable` bool) and score deterministically first: normalised exact match or contains-match for IDs and numbers, citation correctness (does a cited source map to the `expect` file?), and abstention accuracy on unanswerable questions. Add an LLM-as-judge faithfulness check only for free-form answers. RAGAS works with local models but adds heavy dependencies and has had reliability issues with small judges.

### Cited Findings
- RAGAS faithfulness uses an LLM to extract statements from the answer and then checks each against the retrieved context. A high score means the answer is well grounded. — [Red Hat OpenShift AI docs, Evaluating RAG with Ragas](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.4/html/evaluating_ai_systems/evaluating-rag-systems-with-ragas_evaluate); [mljourney](https://mljourney.com/?p=6665)
- RAGAS defaults to an OpenAI judge. Local use requires wrapping an Ollama model (for example llama3.1:8b) via LangChain wrappers. One blog recommends at least a 13B judge for reliable scoring, which is a rule of thumb, not official guidance. — [aiexpjourney substack](https://aiexpjourney.substack.com/p/advanced-rag-03-using-ragas-llamaindex-for-rag-evaluation-84756b82dca7)
- A RAGAS GitHub issue reports faithfulness returning NaN with a local Ollama llama3.1 judge. — [ragas issue #1274](https://github.com/explodinggradients/ragas/issues/1274)
- Each faithfulness sample costs about 2 judge calls. — [mljourney](https://mljourney.com/?p=6665)
- GRAB-RAG's evaluation design (the same questions under supportive, degraded, missing and misleading contexts) is a template for testing abstention vs correctness separately. — [alphaXiv 2608.22228](https://alphaxiv.org/abs/2608.22228v1)
- LIT-RAGBench evaluates generator capabilities including insufficient-evidence abstention and flags over-abstention as a failure, so evals should score both false answers and false refusals. — [arXiv 2603.06198](https://arxiv.org/pdf/2603.06198)

### Inferences
- Proposed `labrador eval --answers` metrics, all computable without an LLM:
  - **answer_em**: normalised (case, whitespace, punctuation) gold string contained in the answer. This suits IDs, dates and amounts, which dominate personal lookups.
  - **citation_hit**: at least one cited `[n]` maps to a file whose stem equals `expect`.
  - **citation_precision**: share of cited sources that are the `expect` file (penalises citation spam).
  - **abstain_acc**: on `answerable: false` rows, the answer is the fixed refusal sentence. Report false-answer rate and false-refusal rate separately.
  - **unverified_rate**: share of answers that fail the verbatim-number check (from section 5).
  - Report the existing retrieval hit@5 alongside, to separate retrieval misses from generation misses (answer wrong but `expect` was in the context = generator failure).
- Unanswerable rows are easy to add to the fictional benchmark: ask for facts that are not in the folder ("what is my blood type?"), and near-miss facts (folder has a passport, ask for a driver's licence number). These approximate GRAB-RAG's missing and misleading conditions.
- Misleading-context tests specific to personal files: include an expired and a current document of the same type and ask for the current one. This tests date metadata use and conflict reporting.
- Judge model: if an LLM judge is used for free-form answers, use a different and larger local model than the generator where possible, ask a binary "is every claim supported by the cited sources?" question, and log raw judgements to `evals/out/` (per CLAUDE.md). A ~30-line judge in the harness is more transparent than RAGAS for a learning tool. DeepEval was in scope but I found no 2025–2026 primary source on its local-model use, so it is not assessed here.
- Following repo convention: commit the harness and a written `REPORT.md`, keep raw outputs in gitignored `evals/out/`, and record the LLM model name, quantisation and temperature in each output file, since answers depend on them in the same way vectors depend on the embedder fingerprint.

### Gaps
- No primary source found on DeepEval with local models in 2025–2026.
- No published agreement rates between small local judges and human labels for RAG faithfulness were found.
- The RAGAS NaN issue resolution was not checked.

---

## Cross-cutting: small local models (4–30B) vs frontier APIs (summary of where advice differs)

### Takeaway
The core pattern (documents first, numbered sources, cite `[n]`, question last, fixed refusal string) is the same as for frontier models. Small models need shorter prompts, fewer sources, temperature 0, constrained JSON only where streaming is not needed, and deterministic code checks instead of trusting self-reported confidence or prompt-only abstention.

### Cited Findings
- Small frozen RAG models (3.8B–8B) abstain reliably on missing evidence but not on misleading evidence, even with explicit abstention prompts and CoT. — [alphaXiv 2608.22228](https://alphaxiv.org/abs/2608.22228v1)
- Purpose-trained small RAG models (Pleias-RAG 1B) report competitiveness with 4–8B general models on multi-hop QA with literal-quote citations. — [arXiv 2504.18225](https://arxiv.org/abs/2504.18225)
- Long contexts degrade performance even for long-context models. — [arXiv 2307.03172](https://arxiv.org/abs/2307.03172)
- Structured output via JSON schema is supported locally (Ollama `format`) but should be validated, at low temperature. — [Ollama blog](https://registry.ollama.ai/blog/structured-outputs); [glukhov.org](https://www.glukhov.org/post/2025/09/llm-structured-output-with-ollama-in-python-and-go/)

### Inferences
- Suggested module shape (about 150–200 lines, consistent with labrador's style):
  - `keywords(question) -> str`: stopword strip, no LLM.
  - `retrieve(store, emb, question, k) -> list[Hit]`: `search()` with dense on the question and BM25 on the keywords. This needs a small `search()` change to accept a separate `keyword_query` argument, which preserves the existing RRF.
  - `pack(store, hits, budget) -> (prompt_sources, sources_meta)`: expand groups, truncate, number sources, add metadata.
  - `generate(llm, system, sources, question, stream=True)`: OpenAI-compatible POST, yields tokens. Use a `FakeLLM` for tests.
  - `check(answer, sources) -> dict`: citation parse, verbatim-number check, optional MRZ checksum.
  - `ask` CLI command (`labrador ask "..." [--k 5] [--model ...] [--json] [--images]`) and a `/api/ask` web endpoint streaming SSE.
- Model guidance (inference; not benchmarked here): 4B models are usable for single-fact extraction with 3–5 short sources; 8–14B are noticeably safer for citation discipline and conflict reporting; a VLM such as Qwen3-VL-8B can double as generator and image reader.

### Gaps
- No up-to-date (2025–2026) benchmark found that ranks specific 4–30B local models on grounded RAG answering with citations. Choosing the default model should be an experiment on labrador's own benchmark.
