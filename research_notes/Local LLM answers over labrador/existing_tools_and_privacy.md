# Existing local "chat with your documents" tools, and privacy/security for answering over sensitive personal documents

Scope: (a) how mature local RAG tools wire retrieval to a local LLM, what labrador could borrow, and whether to expose labrador's retriever to an existing assistant (MCP) instead of building an `ask` command; (b) a privacy and security checklist for answering questions such as "what's my passport number?" from passports, IDs and financial records on macOS. Research date: 2026-11-02. Many project-status claims come from aggregators; that is flagged inline.

## How do existing local RAG tools wire retrieval to a local LLM (backend, prompts, citations, multimodal, streaming, "not found"), what is their status, and what do users complain about?

### Takeaway
Nearly every tool has converged on the same minimal pattern: an OpenAI-compatible chat endpoint (Ollama / llama.cpp / LM Studio / vLLM) as the backend abstraction, top-k retrieved chunks inserted into a fixed RAG prompt with numbered `<source id=…>` tags, instructions to cite `[id]` and to say "I don't know" when context is missing, and streamed output. The most common failure users hit is not the LLM but the plumbing around it: the local model's small default context window silently truncating retrieved context, weak embeddings, and retrieval returning empty context. Several projects in this space are now archived or stalled (Reor archived; GPT4All apparently stalled), which argues for labrador keeping the LLM step thin and backend-agnostic rather than tying to one app.

### Cited Findings
**Backend abstraction**
- PrivateGPT (zylon-ai) now presents itself as an API layer between an app and an inference server; it works with "any OpenAI-compatible server" implementing `/v1/chat/completions` and `/v1/models`, naming Ollama, llama.cpp and vLLM; embeddings use a separate endpoint (`OPENAI_EMBEDDING_API_BASE`). Its current README describes an Anthropic-style API at `localhost:8080` and a demo UI at `/ui`. No releases are listed on the repo page. — [zylon-ai/private-gpt README](https://github.com/zylon-ai/private-gpt)
- PrivateGPT's Ollama docs: Ollama exposes no tokenizer endpoint, so PrivateGPT estimates tokens at 4 chars = 1 token, which can overflow the context window; they recommend setting `context_window` explicitly (e.g. 32768). Ollama API used at `http://localhost:11434/v1`. — [PrivateGPT Ollama docs](https://docs.privategpt.dev/providers/ollama)
- PrivateGPT ships a default query-mode system prompt restricting answers to the provided context, and an `LLM_PROMPT_STYLE` setting (default llama3) for the chat template. — [3x3cut0r/privategpt Docker Hub](https://hub.docker.com/r/3x3cut0r/privategpt) (third-party image docs)
- Khoj points at Ollama or any OpenAI-compatible server through `OPENAI_BASE_URL`; AGPL-3.0. — [promptquorum Khoj review](https://www.promptquorum.com/power-local-llm/khoj-ai-second-brain-review) (third-party)
- Reor talks to Ollama directly and can also use any OpenAI-compatible API. — [reorproject/reor](https://github.com/reorproject/reor)
- LM Studio serves local models over OpenAI-compatible endpoints, optionally on the local network. — [Flathub LM Studio listing](https://flathub.org/ja/apps/ai.lmstudio.lm-studio); [tecnobits guide](https://tecnobits.com/en/Use-LM-Studio-without-an-internet-connection/) (secondary)

**Prompt templates, citations and "not found"**
- Open WebUI's `DEFAULT_RAG_TEMPLATE` (backend/open_webui/config.py): the model answers using a `<context>` block (placeholder `{{CONTEXT}}`) made of `<source>` tags; it adds inline `[id]` citations only when a source tag has an explicit `id`; if it doesn't know, it should say so and may ask for clarification; if the context lacks the answer but the model knows it, it should say the context didn't cover it and answer from its own knowledge; if context is unreadable/low quality it should tell the user; reply in the user's language and don't emit XML tags. — [open-webui config.py](https://raw.githubusercontent.com/open-webui/open-webui/main/backend/open_webui/config.py)
- Open WebUI RAG defaults from the same file: `RAG_TOP_K`=3, `RAG_RELEVANCE_THRESHOLD`=0.0, hybrid search (BM25 weight 0.5) and reranking **off** by default, `CHUNK_SIZE`/`CHUNK_OVERLAP` 1000/100, embedding model `sentence-transformers/all-MiniLM-L6-v2`. — [open-webui config.py](https://raw.githubusercontent.com/open-webui/open-webui/main/backend/open_webui/config.py)
- Open WebUI's RAG template is editable in Admin Panel > Settings > Documents; the formatted context is prepended to the user message; using the `{{QUERY}}` placeholder makes the query appear twice because the query is also appended. — [Open WebUI RAG docs](https://docs.openwebui.com/features/chat-conversations/rag.md)
- AnythingLLM has a "query" mode described as simple QA against your documents with in-chat citations linked to the original document source and text (vs. "chat" mode that can use general knowledge). — [AnythingLLM README mirror](https://github.com/mohnkhan/anything-llm) (mirror of the official README)
- Without a system prompt requiring citations, models tend to summarize without citing sources (observation about PrivateGPT). — [bestllmfor.com PrivateGPT guide](https://bestllmfor.com/guide/privategpt-chatbot-documents-locaux/) (secondary)
- Msty's "knowledge stacks" ground answers in your own files, and Msty Studio can also plug in MCP tools. — [msty.app](https://msty.app); [tooldirectory.ai](https://tooldirectory.ai/tools/msty) (vendor/marketing)

**Context-window pitfalls (the most common complaint)**
- Open WebUI's RAG troubleshooting docs: Ollama models default to a small context (the docs say 2048 tokens), which is "a major bottleneck"; they recommend ≥8192 and 16384+ for complex pages; Open WebUI "aggressively trims" retrieved content to fit; poor embeddings mean the retriever won't pull the right content "no matter how powerful your LLM is". — [Open WebUI RAG troubleshooting](https://docs.openwebui.com/troubleshooting/rag)
- Conflict: Ollama's current FAQ says the default context window is **4096** tokens, settable globally with `OLLAMA_CONTEXT_LENGTH` or per request with `options.num_ctx`. The 2048 figure in Open WebUI's docs is likely from older Ollama versions. — [Ollama FAQ](https://docs.ollama.com/faq.md)
- Open WebUI issue #10747 (v0.5.16): "Focused Retrieval" often produced an **empty context**, so the LLM couldn't answer questions about uploaded documents; disabling it fixed the issue. — [open-webui issue #10747](https://github.com/open-webui/open-webui/issues/10747)
- Ollama unloads models after 5 minutes by default (`OLLAMA_KEEP_ALIVE`, or per-request `keep_alive`; 0 = unload right after the response). — [Ollama FAQ](https://docs.ollama.com/faq.md)

**Project status (2025–2026)**
- Reor: GitHub repository archived by the owner on 2026-03-07 (read-only). — [reorproject/reor](https://github.com/reorproject/reor); [itechguides review 2026](https://www.itechguides.com/machine-learning-in-linux-reor-ai-note-taking-app-review-and-setup-guide-2026/)
- GPT4All: latest release v3.10.0, Feb 2025 per the releases page; a 2026 guide says gpt4all.io now redirects to Nomic's enterprise platform and users should not expect new features. Latest LocalDocs work found was in the 3.4.x releases (Oct 2024: indexing fixes, .docx support). Treat as stalled, not officially abandoned. — [nomic-ai/gpt4all releases](https://github.com/nomic-ai/gpt4all/releases); [bestllmfor.com GPT4All guide](https://bestllmfor.com/guide/gpt4all-premiers-pas/) (secondary)
- Khoj: hosted Khoj Cloud reportedly sunset 2026-04-15; open-source repo not archived, last commit ~2026-08-02, last release 2026-03-26, ~37k stars. — [promptquorum review](https://www.promptquorum.com/power-local-llm/khoj-ai-second-brain-review); [ideaproof.io](https://ideaproof.io/open-source/project/khoj) (both third-party)
- PrivateGPT: maintained by the Zylon team; the README invites PRs but shows no releases; air-gapped operation is marketed as a Zylon (commercial) feature. — [zylon-ai/private-gpt](https://github.com/zylon-ai/private-gpt); [PrivateGPT intro](https://docs.privategpt.dev/introduction.md)
- Open WebUI: active; RAG documentation updated through 2026 (e.g. a NETWAYS blog post dated 2026-04-08). — [NETWAYS blog](https://nws.netways.de/en/blog/2026/04/08/retrieval-augmented-generation-rag-in-open-webui/)

### Inferences
- **Backend:** labrador needs only one backend, an OpenAI-compatible `/v1/chat/completions` client pointed at a configurable base URL (default `http://127.0.0.1:11434/v1` for Ollama; LM Studio and llama.cpp `llama-server` speak the same protocol). That is the abstraction PrivateGPT, Khoj, Reor and AnythingLLM all converge on, and it can be a ~30-line `httpx` call with `stream=True`, with no LangChain/LlamaIndex dependency. This fits the "every stage visible" ethos.
- **Prompt:** borrow Open WebUI's structure: `<source id="1" file="…" page="…">…</source>` blocks, cite `[1]`, and say "not found in your documents" when the answer is missing. For sensitive lookups, **drop** Open WebUI's "answer from your own knowledge" fallback: a passport number must come only from the context, or the model hallucinates a plausible-looking number. Use AnythingLLM's "query mode" (context-only) as the default.
- **"Not found":** labrador can decide "not found" before calling the LLM by using its own score signal (e.g. a fused-score/z-score floor), instead of relying on the model. Open WebUI's default relevance threshold of 0.0 shows the others mostly don't.
- **Context window:** with Ollama's 4096-token default, labrador must budget explicitly. Count roughly how much retrieved text it sends, pass `num_ctx` (Ollama-native API) or warn, and never silently trim. Silent truncation is the single most reported RAG failure.
- **Multimodal:** labrador already turns images and scanned pages into OCR text units. The simplest `ask` sends OCR text plus file/page references. Sending page images to a local VLM (e.g. Gemma 3 / Qwen-VL via Ollama) is an optional second step; passports have an MRZ, which is often better read from OCR text than by a small VLM (unverified, see Gaps).
- labrador already has things these tools ship with off by default (hybrid BM25 + RRF), which matters for exact-identifier questions like passport numbers.

### Gaps
- Could not retrieve Khoj's, GPT4All LocalDocs' or LlamaIndex/LangChain's exact current QA prompt templates from primary sources within budget. (From prior knowledge, unverified here: LlamaIndex's default text-QA prompt is "Context information is below… Given the context information and not prior knowledge, answer the query.")
- Did not find a primary source on how any of these tools handle multimodal (image/page-image) context for answering, or on VLM accuracy for reading ID numbers.
- User-complaint evidence is limited to Open WebUI docs and one issue. Did not survey AnythingLLM, Khoj or PrivateGPT issue trackers systematically.
- AnythingLLM's exact "no relevant information" fallback text in query mode was not found.

## Could labrador expose its retriever to an existing local assistant (MCP server / tool) instead of building an `ask` command?

### Takeaway
Yes. MCP is now supported by local hosts (LM Studio is an MCP host with per-call confirmation dialogs; Msty supports MCP tools; Claude Desktop is the reference host). A `labrador mcp` stdio server exposing a single `search` tool is small and reuses `search.py` unchanged. But it hands control of answer formatting, logging and egress to the host app, and when the host is a cloud model (Claude Desktop) your passport text leaves the machine. A built-in `ask` command is the only route where labrador can guarantee local-only inference, a context-only prompt and redaction. Reasonable plan: build `ask` for the private path, and optionally add an MCP server documented as "only use with a local-model host".

### Cited Findings
- MCP tools are "model-controlled"; the spec says there SHOULD always be a human in the loop able to deny tool invocations, and applications SHOULD show which tools are exposed, indicate invocations, and confirm operations. — [MCP spec 2025-06-18: Tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)
- Tool definition = `name`, `title`, `description`, `inputSchema` (JSON Schema), optional `outputSchema` and `annotations`; results can carry `text`, `image` (base64 + mimeType), `resource_link` (e.g. `file:///…` URI) and embedded resources, plus `structuredContent` (which SHOULD also be serialized into a text block). Annotations support `audience: ["user"|"assistant"]`. — [MCP spec: Tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)
- Security considerations in the spec: servers MUST validate inputs, implement access controls, rate-limit and sanitize outputs; clients SHOULD confirm sensitive operations, show tool inputs to the user "to avoid malicious or accidental data exfiltration", validate results before passing them to the LLM, and log tool usage. Clients MUST treat tool annotations as untrusted unless from trusted servers. — [MCP spec: Tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)
- LM Studio is an MCP host, configured with Cursor-style `mcp.json`, and spawns a separate process per server. When a model calls a tool, LM Studio shows a confirmation dialog where the user can review and edit the arguments; "always allow" is possible and can be managed later in App Settings > Tools & Integrations. LM Studio warns that some MCP servers can run arbitrary code, access local files and use the network. — [LM Studio blog: MCP in LM Studio](https://www.lmstudio.ai/blog/mcp)
- Tool calling depends on the model: you need a model tagged for tool use/function calling. — [apidog guide](https://apidog.com/es/blog/lmstudio-mcp-server/) (secondary)
- Willison: MCP "encourages users to mix and match tools from different sources", which makes it easy to assemble the lethal trifecta; he cites a GitHub MCP exploit. — [Simon Willison, The lethal trifecta (2025-06-16)](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/)
- Ollama has cloud models and web search features that can be disabled (see privacy section). A host app using Ollama may therefore not be purely local unless configured. — [Ollama FAQ](https://docs.ollama.com/faq.md)

### Inferences
- **MCP route** (`labrador mcp`, stdio transport, one `search(query, k, only)` tool returning top units as text plus `resource_link`s to `file://…#page=N`):
  - Pros: ~50–100 lines (Python `mcp` SDK); no prompt/LLM code in labrador; users get the host's chat UI, streaming and model choice; composes with other tools.
  - Cons: labrador loses control over (1) which model sees the data (could be cloud), (2) the host's chat-history storage and logs, (3) markdown/image rendering (an exfiltration channel), (4) other tools in the same session that can talk to the network (trifecta). Small local models are also unreliable at deciding to call tools.
- **`ask` route** (`labrador ask "…"`, plus an optional web UI box): ~100–150 lines. Retrieve, check the score threshold, build a context-only prompt, stream from a localhost OpenAI-compatible endpoint, print citations from labrador's own metadata (not model-generated paths), and redact by default. It keeps every stage visible, which matches CLAUDE.md's teaching goal.
- An `ask` can still be offered through MCP later. The safety-relevant code (endpoint allow-list, redaction, no-history) should live in labrador either way.
- Integrating into Open WebUI/AnythingLLM as the RAG engine instead of labrador would discard labrador's hybrid/multimodal retrieval for their simpler defaults (top-k 3, MiniLM, hybrid off). Not recommended for a learning project.

### Gaps
- Did not verify current MCP support or confirmation UX in Ollama's own desktop app or in Open WebUI (Open WebUI supports tools/OpenAPI servers; MCP support details were not checked).
- Did not check the newest MCP spec revision after 2025-06-18 for changes to the tools section.

## Privacy: how to guarantee no network egress, and handle logging/caching, LAN exposure and index file permissions?

### Takeaway
"Local" is a configuration, not a property. Ollama binds to 127.0.0.1:11434 by default, but it has cloud models and web search that must be turned off (`OLLAMA_NO_CLOUD=1`), and it auto-updates. LM Studio can serve on the LAN. labrador should refuse non-loopback LLM endpoints by default, bind its web UI to 127.0.0.1 only, write no prompts or answers to disk, and create the index directory with owner-only permissions, because the index already contains OCR'd passport text.

### Cited Findings
- Ollama binds 127.0.0.1:11434 by default; change with `OLLAMA_HOST`. CORS allows 127.0.0.1 and 0.0.0.0 origins by default; others via `OLLAMA_ORIGINS`. — [Ollama FAQ](https://docs.ollama.com/faq.md)
- Ollama local-only mode: set `disable_ollama_cloud: true` in `~/.ollama/server.json` or `OLLAMA_NO_CLOUD=1`, then restart; the logs should show "Ollama cloud disabled: true". This disables cloud models and web search. — [Ollama FAQ](https://docs.ollama.com/faq.md); [Ollama Cloud docs](https://docs.ollama.com/cloud.md)
- Ollama says it doesn't see prompts for local use; for cloud models, prompts are processed but not stored/logged; it collects "basic account info and limited usage metadata". The FAQ doesn't say whether prompts are logged locally. — [Ollama FAQ](https://docs.ollama.com/faq.md)
- Notebookcheck: the cloud toggle affects only Ollama; Ollama auto-downloads updates on macOS/Windows; its privacy policy allows collecting app version, request counts and IP but not content; guides telling you to set `OLLAMA_HOST=0.0.0.0` expose the model to every device on the network. — [Notebookcheck: making sure local AI stays offline](https://www.notebookcheck.net/Ollama-and-LM-Studio-How-to-make-sure-your-local-AI-stays-offline.1435420.0.html)
- LM Studio: once models are downloaded, inference runs fully offline; internet is needed only for model downloads/updates; "Local Network Serving" exposes models to other devices on the network. Third-party sources say it doesn't collect user data (unverified against LM Studio's own privacy policy). — [tecnobits guide](https://tecnobits.com/en/Use-LM-Studio-without-an-internet-connection/); [Flathub listing](https://flathub.org/ja/apps/ai.lmstudio.lm-studio) (secondary)
- AnythingLLM sends telemetry (PostHog) by default; opt out with `DISABLE_TELEMETRY=true` or in-app Privacy settings. — [AnythingLLM README mirror](https://github.com/mohnkhan/anything-llm)
- Msty claims zero telemetry and offline use with local models; marketing copy, no independent audit found. — [msty.app](https://msty.app); [tooldirectory.ai](https://tooldirectory.ai/tools/msty)
- Open WebUI has knowledge-file retention, local web fetch and similar settings in config (e.g. `ENABLE_KNOWLEDGE_FILE_RETENTION`, `ENABLE_LOCAL_WEB_FETCH` default False), showing chat UIs persist uploaded files and conversations server-side. — [open-webui config.py](https://raw.githubusercontent.com/open-webui/open-webui/main/backend/open_webui/config.py)
- labrador's own web UI already serves on `http://127.0.0.1:8765`, and its index lives in `~/.labrador/indexes/<folder>-<hash>/` with `index.db` + `media/` thumbnails. — [labrador README](../../README.md)

### Inferences — privacy checklist for labrador `ask`
1. **Endpoint allow-list:** accept only loopback LLM base URLs (`127.0.0.1`, `::1`, `localhost`) by default. Anything else needs an explicit `--allow-remote-llm` flag and a printed warning. Resolve the hostname and check the IP, not just the string.
2. **Document the runtime settings:** `OLLAMA_NO_CLOUD=1`; do not set `OLLAMA_HOST=0.0.0.0`; in LM Studio, keep "serve on local network" off. Optionally `labrador ask --check` queries the endpoint and warns if the model name looks like a cloud model (Ollama cloud models are suffixed `-cloud`; that convention is from prior knowledge, verify).
3. **No persistence of Q/A:** don't write questions, retrieved context or answers to any file, log, SQLite table or shell history helper. No answer cache. Keep the existing `--json` output on stdout only. Short `keep_alive` (or `0`) reduces how long context sits in the runtime's memory (minor).
4. **Web UI:** keep the bind at 127.0.0.1. Refuse `--host 0.0.0.0` unless explicitly forced. Add a Host-header check against DNS rebinding and no permissive CORS, since any local web page could otherwise POST to `127.0.0.1:8765/ask`. Ollama's own CORS default only trusts localhost origins, a model to copy. Serve answers with `Cache-Control: no-store`.
5. **Index file permissions:** `~/.labrador` at `0700`, `index.db` and `media/` at `0600`/`0700`. The OCR text and thumbnails of a passport are as sensitive as the passport scan. Consider excluding `~/.labrador` from Time Machine/Spotlight, or at least documenting that it holds sensitive data. FileVault covers data at rest.
6. **Network egress verification:** for the learning-oriented README, show how to verify with `lsof -i -P | grep -E 'ollama|python'` or Little Snitch/LuLu while running `ask`, rather than claiming a guarantee.
7. **Model download and auto-update** are the remaining egress paths; they are content-free but should be disclosed.

### Gaps
- Could not find LM Studio's own primary privacy policy text or its telemetry settings within budget; claims above are secondary.
- Did not confirm whether Ollama writes prompt content to `~/.ollama/logs/server.log` at default or debug (`OLLAMA_DEBUG=1`) log levels. Worth testing locally.
- DNS-rebinding/CORS risk against localhost web UIs is from general web-security knowledge; no specific source collected here.

## Security: indirect prompt injection from indexed documents, and risks when the LLM has tools

### Takeaway
Any indexed file is untrusted input: a PDF, a screenshot or OCR'd image text can carry instructions. Injection cannot be reliably prevented (OWASP LLM01 ranks it #1; Willison: "we still don't know how to 100% reliably prevent this"). The defense that works is architectural: never combine private data + untrusted content + an exfiltration channel. For a read-only `ask` with no tools, the realistic harms shrink to (a) a misleading answer and (b) exfiltration via rendered markdown images/links in the web UI. Both are cheap to close.

### Cited Findings
- Willison's "lethal trifecta" (2025-06-16): access to private data + exposure to untrusted content + ability to communicate externally makes an agent exploitable by prompt injection; LLMs cannot reliably distinguish instructions by source; guardrails are unreliable; avoid combining all three. — [Simon Willison, The lethal trifecta](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/)
- Markdown image exfiltration: if a chat interface renders Markdown images and is exposed to private + untrusted data, "you have a data exfiltration prompt injection vulnerability". Examples include ChatGPT (2023), Bard, Writer.com, Amazon Q, NotebookLM, Mistral LeChat (patched by locking down Markdown images), GitLab Duo (2025, fixed by allowing only trusted domains in links/images); GitHub Copilot Chat disabled image references to untrusted domains. — [Willison 2023-04-14](https://simonwillison.net/2023/Apr/14/new-prompt-injection-attack-on-chatgpt-web-version-markdown-imag/); [Willison 2024-10-22 Imprompter](https://simonwillison.net/2024/Oct/22/imprompter/); [Willison 2025-05-23 GitLab Duo](https://simonwillison.net/2025/May/23/)
- OWASP Top 10 for LLM Applications 2025: LLM01 Prompt Injection (direct and indirect, e.g. external content instructing the model) is #1; suggested mitigations include limiting model access to backend systems and segregating external content from user prompts. LLM02 Sensitive Information Disclosure (PII, financial, health, credentials) rose from #6 (2023) to #2; mitigations include redaction and input/output scrubbing. — [HackerOne on OWASP LLM 2025](https://www.hackerone.com/ai/owasp-top-10-llms-2025); [Infosecurity Magazine](https://www.infosecurity-magazine.com/news/owasp-data-exposure-risk-ai/)
- One source says OWASP now lists a 2026 edition as current. Check numbering before citing. — [Modulos docs](https://docs.modulos.ai/frameworks/owasp-top-10-llm)
- Spotlighting (Microsoft Research, Hines et al. 2024, arXiv 2403.14720): delimiting with randomized markers, datamarking (interleaving a special token throughout untrusted text) and encoding; datamarking and encoding had negligible task-performance cost and cut indirect-injection success from >50% to <2% in Microsoft's tests. An open implementation notes it "does not hold up against determined adaptive adversaries". — [arXiv 2403.14720](https://arxiv.org/html/2403.14720v1); [realArcherL/spotlighting-datamarking](https://github.com/realArcherL/spotlighting-datamarking)
- MCP spec: clients SHOULD show tool inputs before calling, to avoid exfiltration; servers MUST sanitize outputs. — [MCP spec: Tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)
- LM Studio's tool-call confirmation lets users review/edit arguments; "always allow" weakens this. — [LM Studio MCP blog](https://www.lmstudio.ai/blog/mcp)

### Inferences — security checklist for labrador `ask`
1. **No tools for the answering LLM.** `ask` is a single completion call: no function calling, no web fetch, no file writes. This removes the "act" and most of the "communicate" legs of the trifecta.
2. **Render answers as plain text.** In the CLI, print raw text. In the web UI, insert with `textContent` (no Markdown/HTML rendering), or if Markdown is wanted, strip images and links to anything but labrador's own `/file/...` routes. Add a strict CSP (`img-src 'self'`, `connect-src 'self'`) as backstop.
3. **Citations from metadata, not from the model.** The model outputs `[n]`; labrador maps `n` to file path/page from its own retrieval results, and drops indices that weren't provided. The model never produces paths or URLs that get opened.
4. **Spotlight retrieved text.** Wrap each chunk in `<source id=n>` with a randomized delimiter nonce, and state in the system prompt that source text is data and may contain instructions to ignore. This is cheap and visible, but document it as risk reduction, not a guarantee.
5. **Show sources next to the answer** (snippets/thumbnails), so a user can see when an answer came from a suspicious file. This also helps against hallucinated IDs.
6. **If an MCP server is added:** read-only `search` tool only, validate `k`/`only` inputs, cap result size, return snippets rather than whole files, and document that pairing it in one session with web/email/fetch tools completes the lethal trifecta.
7. **Threat model note for the README:** the realistic attacker is someone who gets a file into the indexed folder (downloaded PDF, email attachment, shared folder). Indexing a downloads folder raises exposure.

### Gaps
- No source found quantifying injection success against small local models (e.g. 4–12B Gemma/Qwen/Llama) specifically, or injection via OCR'd image text in RAG.
- Did not research Willison's "dual LLM" pattern or Google DeepMind's CaMeL in detail. Both are overkill for a no-tool `ask`.

## Should sensitive answers be masked/redacted by default, or require confirmation? Is there established practice?

### Takeaway
There is no single established standard for local personal-document assistants. OWASP LLM02 recommends output scrubbing/redaction, and the MCP spec recommends human confirmation for sensitive operations. The common UX pattern from password managers (masked value with click to reveal/copy) is a good fit. Pattern detectors such as Microsoft Presidio exist but are noisy for generic 9-digit numbers. Suggested default for labrador: show the answer with detected identifiers masked (e.g. `X1234****`), reveal on an explicit `--reveal` flag or click, and never mask the cited source location.

### Cited Findings
- OWASP LLM02 mitigations include redaction and input/output scrubbing of sensitive data. — [HackerOne on OWASP LLM 2025](https://www.hackerone.com/ai/owasp-top-10-llms-2025); [Infosecurity Magazine](https://www.infosecurity-magazine.com/news/owasp-data-exposure-risk-ai/)
- MCP spec: clients SHOULD prompt for user confirmation on sensitive operations. — [MCP spec: Tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)
- Microsoft Presidio: an analyzer detects entities (pattern + context words) and an anonymizer replaces them with placeholders (`<PERSON>`, `<EMAIL_ADDRESS>`…); a US passport recognizer (9-digit, including next-gen format) is listed as enabled by default, with Italian and Indian passport recognizers too (third-party DeepWiki listing). — [DeepWiki: Presidio supported entities](https://deepwiki.com/microsoft/presidio/4-supported-entities) (third-party, auto-generated)
- Presidio FAQ: some recognizers are inherently non-specific ("A driver's license number… could be any 9-digit number"); tune thresholds and context words to manage false positives/misses. — [Presidio FAQ](https://microsoft.github.io/presidio/faq/)
- Presidio has an OCR image-redaction component (`presidio-image-redactor`). — [Docker Hub: microsoft/presidio-ocr](https://hub.docker.com/_/microsoft-presidio-ocr)

### Inferences
- **Mask by default, reveal deliberately.** The user asked the question, so a confirmation prompt before answering adds friction without protecting against much. The real risks are shoulder-surfing, terminal scrollback, screen sharing and screenshots. Mask detected identifiers in the displayed answer (keep the last 3–4 characters), with `labrador ask --reveal` / a "reveal" button / copy-to-clipboard. This mirrors password managers and does not depend on the LLM cooperating.
- **Detect with simple, visible rules** rather than a heavy dependency: regexes for passport MRZ lines (`P<…`), long digit/alnum runs (≥6 chars with digits), IBAN/card-like numbers (with a Luhn check), SSN patterns. Apply them to the model's output, and also treat exact substrings copied from a retrieved unit as candidates. Presidio is an optional upgrade, but it pulls spaCy models and is noisy. A small regex module is more in keeping with labrador's ~1,200-line ethos.
- **Never let masking hide provenance:** always show which file/page the value came from, so the user can open the original to verify. LLM transcription errors in ID numbers are a real risk.
- **Masking vs. verbatim extraction:** for ID-number questions, it may be more reliable to return the matching OCR span directly from the retrieved unit (labrador's BM25/units already locate it) and use the LLM only to pick which span answers the question. This reduces hallucinated digits. Untested idea.
- Redact before **any** persistence too (there should be none; see the privacy checklist) and in the `--json` output unless `--reveal` is given.

### Gaps
- Found no published UX guideline or study specific to masking LLM answers in personal-document assistants. The recommendation above is reasoned from password-manager practice and OWASP, not an established standard.
- Did not verify Presidio's passport recognizers against the official repo (the DeepWiki source is auto-generated).
- No source on how often small local LLMs mis-transcribe long identifiers from context. Worth measuring with labrador's benchmark (add ID-lookup queries with exact-match scoring).
