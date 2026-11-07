# Local LLM runtimes and model choices for labrador's grounded QA step (as of Nov 2026)

## Runtimes: Ollama, llama.cpp, MLX (mlx-lm / mlx-vlm), LM Studio, transformers, Apple Foundation Models

### Takeaway
Every serious local runtime now exposes an OpenAI-compatible `/v1/chat/completions` endpoint with streaming, so the runtime can be a user choice. Ollama has the smoothest install and model management, supports JSON-schema structured output and vision, and since v0.19 (Mar 2026) runs on MLX on Apple Silicon. mlx-lm and mlx-vlm are the fastest in-process option. llama.cpp's `llama-server` is the lowest-level and most portable option.

### Cited Findings
**Ollama**
- Ollama 0.19 (March 30, 2026) is "built on top of Apple's machine learning framework, MLX" on Apple Silicon. It was a preview at first, limited to Qwen3.5-35B-A3B (NVFP4) on Macs with more than 32 GB. Decode went from 58 to 112 tok/s and prefill from 1154 to 1810 tok/s, comparing 0.19 NVFP4 with 0.18 Q4_K_M; the chip is not named. M5 chips additionally use GPU "Neural Accelerators". — [Ollama blog: MLX](https://ollama.com/blog/mlx)
- A later write-up says Ollama 0.30 improved its llama.cpp path alongside the MLX engine. This is a secondary source and I did not verify it. — [classmethod deep dive](https://dev.classmethod.jp/en/articles/apple-mlx-ollama-deep-dive/)
- The Ollama library now has `-mlx` tags for Gemma 4. For example, `gemma4:e4b` is 6.6–9.5 GB, `gemma4:12b` is about 7.7–8 GB, `gemma4:26b` is 16–19 GB and `gemma4:31b` is 19–20 GB. Context is 128K for E2B/E4B and 256K for the others, and every tag takes text and image input. — [ollama.com/library/gemma4](https://ollama.com/library/gemma4)
- Structured outputs: pass a JSON schema (e.g. Pydantic `model_json_schema()`) in `format`, or use `response_format` on the OpenAI-compatible API. This works with vision models too, and the docs recommend temperature 0. Ollama's cloud does not support it. — [Ollama docs: structured outputs](https://docs.ollama.com/capabilities/structured-outputs)
- Some third-party comparison pages still say Ollama uses only llama.cpp/Metal and not MLX. These pages are outdated. — [PromptQuorum](https://www.promptquorum.com/local-llms/mlx-vs-ollama-vs-llama-cpp-mac), contradicted by [Ollama blog](https://ollama.com/blog/mlx)

**llama.cpp (`llama-server`)**
- `llama-server` offers OpenAI-compatible chat completions, responses and embeddings routes, plus an Anthropic Messages-compatible route. — [llama.cpp server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- It supports schema-constrained JSON (the `json_schema` option, `-j/--json-schema`, and GBNF `grammar`) and SSE streaming. — [llama.cpp server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- Multimodal input via `--mmproj` is marked "experimental" but works on the OpenAI chat endpoint. `-hf user/model[:quant]` downloads from Hugging Face, defaults to Q4_K_M, and fetches the matching mmproj automatically. — [llama.cpp server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)

**MLX: mlx-lm and mlx-vlm**
- mlx-lm (MIT) installs with `pip install mlx-lm` and exposes a Python API (`load`, `generate`, `stream_generate`), with samplers and `logits_processors`. It can convert and quantize with `mlx_lm.convert -q`, and quantized models are published under the `mlx-community` org on Hugging Face. — [mlx-lm GitHub](https://github.com/ml-explore/mlx-lm)
- `mlx_lm.server` implements `/v1/chat/completions` and `/v1/models` with streaming. Its own docs say it "is not recommended for production as it only implements basic security checks." Its SERVER.md does not document `response_format` or JSON schema. — [mlx-lm SERVER.md](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/SERVER.md)
- mlx-vlm (MIT, `pip install -U mlx-vlm`) runs VLMs on Apple Silicon and has a Python API (`load`, `apply_chat_template`, `generate` with images). It also ships a FastAPI OpenAI-compatible server (`mlx_vlm.server`, port 8080) with continuous batching and prefix caching. Supported models include the Gemma 4 sizes and the Qwen2/2.5/3-VL and Qwen3.5 models. — [mlx-vlm GitHub](https://github.com/Blaizzy/mlx-vlm)
- Speed: one independent M4 Max test of Qwen3.5-35B-A3B measured mlx-lm at about 131.8 tok/s, raw llama.cpp at 72 and pre-MLX Ollama at 48. The quantizations differed. — [gitconnected article](https://levelup.gitconnected.com/ollama-mlx-nearly-doubles-llm-speed-on-your-mac-58-to-112-tok-s-and-your-old-models-get-none-of-fd1a9ec531fb)
- One guide claims MLX is 20–87% faster than llama.cpp below about 14B parameters. It says the gap closes at 27B and above, where memory bandwidth limits both, and that MLX time-to-first-token grows with prompt length. This is a secondary blog. — [Starmorph guide](https://blog.starmorph.com/blog/apple-silicon-llm-inference-optimization-guide)

**LM Studio**
- LM Studio's server is on `localhost:1234`, started from the GUI or with `lms server start`. It supports OpenAI-format structured output, using llama.cpp grammars for GGUF models and Outlines in mlx-engine for MLX models. — [LM Studio docs: structured output](https://lmstudio.ai/docs/advanced/structured-output)
- LM Studio 0.4.0 (Jan 2026) added `llmster`, a headless daemon. Later releases reportedly added an Anthropic-compatible API and LM Link. These details come from secondary sources and I did not verify them. — [kunalganglani.com](https://www.kunalganglani.com/blog/lm-studio-vs-ollama)
- LM Studio is a GUI app and is not open source; only its engine (mlx-engine) is. I did not open a primary licence page, so treat this as background knowledge.

**Hugging Face transformers**
- The Qwen3.5 model cards list `transformers serve` (an OpenAI-compatible server) among the official serving options, alongside vLLM and SGLang. They say llama.cpp, Ollama and LM Studio work through community quantizations. — [Qwen/Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B)

**Apple Foundation Models (on-device Apple Intelligence model)**
- Apple publishes an official `apple-fm-sdk` Python package, in beta. It needs macOS 26+, Xcode 26+ and Apple Intelligence enabled, and its main stated purpose is evaluating Swift app features from Python. — [Apple FM SDK docs](https://apple.github.io/python-apple-fm-sdk/), [Getting started](https://apple.github.io/python-apple-fm-sdk/getting_started.html)

### Inferences
- **Recommended abstraction:** an OpenAI-compatible chat endpoint (`base_url` plus `model`) called with plain `httpx` or the `openai` client. Ollama (port 11434/v1), llama-server (8080), LM Studio (1234), mlx_lm.server, mlx_vlm.server and `transformers serve` all speak it. Images go in as base64 `image_url` content parts. This keeps labrador to roughly 50 lines of generation code with a single optional dependency, or none, since `httpx` is already a dev dependency. Models load once in a separate process, so the 1–2 GB EmbeddingGemma process stays light.
- **Default to recommend:** Ollama. It installs with `brew install ollama` or the app, `ollama pull gemma4:e4b` is one command, it manages models, it supports schema-constrained JSON plus vision, and it is MIT-licensed. Use llama-server for users who want no daemon or app.
- **In-process alternative:** an `--extra mlx` that imports `mlx_vlm`. This removes the server but adds a heavier, Mac-only dependency and a second model in labrador's own memory. Torch/MPS (EmbeddingGemma) and MLX would then share unified memory in one process.
- **Not recommended as the primary path:** transformers in-process generation. It already sits in labrador's dependency tree, but MPS generation is slow next to MLX or llama.cpp; I found no benchmark to confirm this. Apple FM SDK is beta, tied to Xcode, uses a closed model and has a small context.
- **Structured output:** Ollama and llama-server enforce JSON schema reliably. For the mlx_lm.server path, the safe choice is plain-text answers with citations in brackets.

### Gaps
- I did not verify whether Ollama's MLX engine now covers vision models such as Gemma 4 `-mlx` tags with image input, beyond the library page listing "Text, Image" for those tags.
- I found no controlled, same-machine benchmark of Ollama-MLX, llama.cpp and mlx-lm for 4B–12B models in 2026.
- I did not confirm the current LM Studio licence terms or the latest mlx-lm/mlx-vlm versions.

## Recommended small/medium models for grounded QA and extraction (sizes, RAM, speed, context)

### Takeaway
The two families to choose from in late 2026 are Gemma 4 and Qwen3.5. Both are Apache 2.0 and natively image-capable, with 128K–262K context. Gemma 4 E4B or Qwen3.5-4B fits an 8–16 GB Mac. Gemma 4 12B or Qwen3.5-9B fits 16–32 GB. Gemma 4 26B-A4B (MoE) or 31B fits 32–64 GB.

### Cited Findings
- Gemma 4 (Apache 2.0) launched around Mar 31 / Apr 2, 2026 in four sizes: E2B, E4B, 26B A4B (MoE) and 31B dense. A "12B Unified" model was added on June 3, 2026, and MTP (multi-token-prediction) variants on Apr 16, 2026. — [Gemma releases](https://ai.google.dev/gemma/docs/releases?hl=en), [Wikipedia](https://en.wikipedia.org/wiki/Gemma_(language_model)). The two sources differ by two days on the launch date.
- Gemma 4 model card details:
  - E2B: 2.3B effective parameters (5.1B with embeddings), 128K context, text, image and audio input.
  - E4B: 4.5B effective (8B with embeddings), 128K, text, image and audio.
  - 12B Unified: 11.95B, 256K, text, image and audio.
  - 26B A4B: 25.2B total with 3.8B active, 256K, text and image.
  - 31B: 30.7B, 256K, text and image.

  — [Gemma 4 model card](https://ai.google.dev/gemma/docs/core/model_card_4). A secondary search summary said the 12B's multimodality was unconfirmed; the model card fetch lists image and audio.
- Qwen3.5 Small (Mar 2, 2026) comes in 0.8B, 2B, 4B and 9B dense sizes under Apache 2.0, with native early-fusion vision (image and video) and 262K context. — [Artificial Analysis](https://artificialanalysis.ai/articles/qwen3-5-small-models), [Gigazine](https://gigazine.net/gsc_news/en/20260303-qwen-3-5-small)
- Qwen3.5-4B context is 262,144 tokens natively, extendable to about 1M with YaRN. Thinking is ON by default (`<think>` output) and is turned off with `enable_thinking: False`. — [Qwen/Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B)
- Speed: Gemma 4 E4B on a base M4 (16 GB) under MLX (oMLX) generates about 33 tok/s at 4K context. An M4 Pro (48 GB) reaches about 40.6 tok/s at 4K, falling to 20.8 tok/s at 128K. These are community-submitted runs with mixed quantizations. — [oMLX benchmarks](https://omlx.ai/benchmarks/6kn71ty3), [another](https://omlx.ai/benchmarks/t34q18ok)
- RAM guidance from Ollama's download sizes (weights only; add KV cache):
  - E2B: about 4.6–7.5 GB.
  - E4B: about 6.6–9.5 GB.
  - 12B: about 8 GB.
  - 26B: about 16–19 GB.
  - 31B: about 19–20 GB.

  — [ollama.com/library/gemma4](https://ollama.com/library/gemma4)

### Inferences
Mac RAM tiers below leave room for macOS plus labrador's EmbeddingGemma process (about 4 GB per the README).
- **8 GB:** Gemma 4 E2B or Qwen3.5-2B, 4-bit. Fine for short grounded answers; weak on reasoning.
- **16 GB:** Gemma 4 E4B or Qwen3.5-4B, 4-bit. This is the sweet spot and gives about 30 tok/s on a base M4.
- **32 GB:** Gemma 4 12B or Qwen3.5-9B, 4-bit or 8-bit.
- **64 GB:** Gemma 4 26B-A4B. As an MoE with about 4B active parameters it runs fast; 31B dense is the more accurate choice.

Other notes:
- For RAG, keep the context short: top-k units plus the question, 2–8K tokens. Prefill time dominates on Macs at long context.
- Turn off Qwen3.5's thinking mode for snappy extraction answers, or strip the `<think>` block.
- I did not research Llama, Phi, Mistral/Ministral or SmolLM in depth. None of them appeared as a 2026 leader in the sources I found for small multimodal models.

### Gaps
- I found no 2026 head-to-head grounded-QA or faithfulness benchmark (e.g. RAG hallucination rate) comparing Gemma 4 and Qwen3.5 small models.
- I did not verify the current Llama, Phi or Ministral small releases for 2026.
- I have no primary-source tok/s numbers for Qwen3.5-4B/9B on M-series chips.

## Vision-language models reading scanned passports and IDs directly

### Takeaway
Small 2026 VLMs are strong document readers. Qwen3.5-4B reports OCRBench 85.0 and Qwen3.5-9B reports OCRBench 89.2; Gemma 4 E4B scores 0.181 on OmniDocBench edit distance. No benchmark covers passports or MRZ codes specifically. The safest design still uses OCR text (Apple Vision) as the primary evidence and the image as a secondary input, and validates MRZ check digits.

### Cited Findings
- Qwen3.5-4B scores OmniDocBench1.5 86.2, CC-OCR 76.7, OCRBench 85.0 and MMLongBench-Doc 54.2. Qwen3.5-9B scores 87.7, 79.3, 89.2 and 57.7 on the same benchmarks. — [Qwen/Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B)
- Gemma 4 OmniDocBench 1.5 edit distance (lower is better): E2B 0.290, E4B 0.181, 12B 0.164, 26B-A4B 0.149, 31B 0.131. — [Gemma 4 model card](https://ai.google.dev/gemma/docs/core/model_card_4)
- PureDocBench (2026) overall scores: Qwen3-VL 2B 66.37, 4B 72.04 and 8B 72.44. — [arXiv 2605.07492](https://arxiv.org/pdf/2605.07492). The table was hard to parse, so verify these numbers.
- Dedicated small OCR models (PaddleOCR-VL, MinerU2.5, GLM-OCR, about 0.9–1.2B) beat even Qwen3-VL-235B on OmniDocBench parsing. — [Roboflow](https://blog.roboflow.com/best-open-source-ocr-models/), [CodeSOTA](https://codesota.com/ocr)
- On MRZ codes: a specialized CNN pipeline reached 99.25% MRZ character macro-F1, and its authors say generic OCR fails to extract MRZ at reasonable accuracy. This is a 2020–2022 paper and predates VLMs. — [Liu et al., arXiv 2009.05489](https://arxiv.org/pdf/2009.05489)
- A community Qwen3-VL-8B ID-extraction fine-tune advises MRZ checksum verification in production. — [CSM-DocExtract-VL card](https://huggingface.co/Chhagan005/CSM-DocExtract-VL-Q4KM/blob/main/README.md)
- Runtime support for the vision models:
  - Ollama: every `gemma4` tag takes images, and structured output works with vision models.
  - llama.cpp: via `--mmproj`, which `-hf` downloads automatically.
  - mlx-vlm: Gemma 4, Qwen3-VL and Qwen3.5.
  - LM Studio: support exists, but I did not verify it per model.

  — sources cited in the runtimes section.

### Inferences
- labrador already stores an OCR-text unit grouped with each image. Feeding the retrieved OCR text plus the original image (downscaled to the model's token budget) to a 4B+ VLM gives two independent reads. The prompt should tell the model to quote only characters visible in the evidence.
- For passport-number questions, cheap deterministic checks catch VLM hallucinated digits: compare against OCR text, and validate the ICAO 9303 MRZ check digits.
- E2B/2B-class models are noticeably worse at documents (E2B 0.290 edit distance against 0.181 for E4B). Recommend at least 4B for image reading.

### Gaps
- I found no benchmark of small local VLMs on passports, ID cards or MRZ codes.
- I found no hallucination-rate data for small VLMs reading low-quality phone photos of documents.

## Does staying in the Gemma family (EmbeddingGemma 2) help?

### Takeaway
There is little technical benefit. The embedder and the generator do not share vectors or weights at inference time. The benefits are softer: a consistent Apache 2.0 licence, the same Google/HF ecosystem, and documentation coherence for a learning codebase. Pick the generator on quality per GB, where Gemma 4 E4B and 12B are competitive with Qwen3.5-4B and 9B.

### Cited Findings
- Gemma 4 is Apache 2.0, the same licence as the EmbeddingGemma 2 model per the labrador README. — [Gemma 4 model card](https://ai.google.dev/gemma/docs/core/model_card_4), labrador README
- Qwen3.5 small models are also Apache 2.0, so licence does not differentiate the two families. — [Qwen/Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B)
- Gemma 4 has first-class `-mlx` tags in Ollama, plus mlx-vlm support. — [ollama.com/library/gemma4](https://ollama.com/library/gemma4), [mlx-vlm](https://github.com/Blaizzy/mlx-vlm)

### Inferences
- A RAG pipeline passes text and images between stages, not embeddings, so a "same family" embedder and generator gives no retrieval-quality coupling.
- Gemma 4 is the natural default for narrative consistency ("all Gemma"), with Qwen3.5 as the documented alternative. Its OCRBench/OmniDocBench numbers at 4B are the strongest found.
- The two families use different chat templates and thinking-mode conventions. With an OpenAI-compatible endpoint the runtime handles both, so labrador's code is the same for either.

### Gaps
- I found no source that measures any benefit from pairing an embedder and a generator of the same family.
