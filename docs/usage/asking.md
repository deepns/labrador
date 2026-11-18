# Asking questions

`labrador ask` answers a question about your indexed folder with a local LLM. It searches the index, hands the top
files to the model as numbered sources, and checks the answer in code before showing it. Nothing leaves your machine.

## Prerequisites

1. An index: `labrador index <folder>` (see the [quick start](quickstart.md)).
2. A local LLM runtime that serves OpenAI-compatible `/v1/chat/completions`. The default is
   [Ollama](https://ollama.com) with `ollama pull qwen3.5:4b`, the model the [QA benchmark](../../evals/answers/REPORT.md) picked. See [Installation](../installation.md#local-answers-optional)
   for model sizes by RAM and the environment variables to set.

## Ask

```bash
labrador ask "what's my passport number"
```

```
Sources
  [1] documents/passport-scan.jpg  (photo OCR, 2025-04-02)
  [2] documents/old-passport.pdf p.1  (PDF page text, 2014-06-11)

Your passport number is •••••02C3 [1]. An older passport, •••••17K9, expired in 2024 [2].

✓ verified against [1] · MRZ check digits valid · high confidence · --reveal to show
```

Options:

```bash
labrador ask "when does my insurance expire" --reveal              # show IDs and numbers unmasked
labrador ask "when does my insurance expire" --json                # structured reply; prints one JSON object, not streamed
labrador ask "my passport number" --model qwen3.5:4b               # another model name
labrador ask "my passport number" --llm-url http://127.0.0.1:8080/v1   # another runtime (llama.cpp, LM Studio)
labrador ask "my passport number" --ctx 8192 -k 8                  # larger prompt budget, more sources
```

`--json` prints one object, `{sources, warnings, answer, check, retried, timings}`, masked unless `--reveal`. It needs a
runtime with structured-output support. Ollama's MLX runner returns an error for it (HTTP 501); use plain asking
there.

`--llm-extra '{"reasoning_effort": "none"}'` passes a JSON object to the runtime, merged over the default
`keep_alive`; this one turns off a model's thinking (Ollama ignores `think` on `/v1`). Thinking is faster off but
cites worse sources, so the default keeps it on. The
defaults also come from `LABRADOR_LLM_URL` and `LABRADOR_LLM_MODEL`. Streaming requests also send
`stream_options: {"include_usage": true}` so the runtime reports token counts; if a runtime rejects it, try
`--llm-extra '{"stream_options": null}'`.

The first question after the model has been idle loads it into memory and can take a minute or two (one answer is
stopped after 5 minutes overall, `llm_deadline_s`, and capped at 2048 tokens, `llm_max_tokens`; override the cap
with `--llm-extra`).

## Reading the result

- **Sources** are the files the model saw, numbered. `[n]` in the answer maps to that list: the path, the page and the
  file's modified date come from the index, never from the model.
- **Warnings** go to stderr when a source was cut to fit, or dropped to stay inside `--ctx`.
- **The timings line** goes to stderr after the status line, so `> answer.txt` stays clean:
  `retrieval 0.21 s · answer 4.8 s · first token 1.2 s · 38 tok/s · 3,480 → 182 tokens`. Retrieval is search plus
  packing, answer is generation, and the token counts are what the runtime reports (never estimated). Anything the
  runtime doesn't report is left out. If the answer hit `llm_max_tokens`, a line says so. `--json` carries the same
  numbers (in milliseconds, `null` when unknown) under `timings`.
- **The status line** reports what labrador checked in code, not what the model claims: the cited sources exist, every
  ID and date in the answer appears verbatim in a cited source, and MRZ check digits on passports are valid.

| Confidence | Meaning |
|---|---|
| `high` | Cited, everything verified, from the top source or a valid MRZ |
| `medium` | Verified, but from a lower-ranked source, or the sources disagree |
| `low` | Something is unverified (`✗ unverified: ...`), a citation doesn't exist, the MRZ is invalid, or there is no citation |
| `refused` | The files don't contain the answer. labrador retries once with the rarest word of your question first |

Treat `low` as "go and look at the source".

## In the web UI

```bash
labrador serve
```

Flip the header toggle from Search to Ask, type a question and press Enter (nothing fires while you type). Sources
link to the file at the right page, and the status line shows the same checks as the terminal. Masked values show as
`•••••02C3`; click one to show it, click again to hide it. `serve` takes the same LLM flags as `ask` (`--model`,
`--llm-url`, `--llm-extra`, `--ctx`, `--allow-remote-llm`) and refuses a non-loopback `--llm-url` the same way.

## Reading pictures (`--images`)

```bash
labrador ask --images "what does the sign say?" --ctx 8192
```

For the top two sources that are images or PDF pages, labrador attaches the original picture (long side 1024 px)
next to the OCR text, so a vision model can read what OCR got wrong. Both default-tier models (`qwen3.5:4b`,
`gemma4:e4b`) are vision models. Each picture adds about 800 prompt tokens. labrador reserves that from `--ctx`, and
the reservation drops text sources if they no longer fit. If you see "dropped" warnings, raise `--ctx` (and
`OLLAMA_CONTEXT_LENGTH`), for example to 8192. Checks still run against the source text, so a value that appears only
in the picture is shown as unverified. Pictures are re-encoded, which drops EXIF/GPS metadata, and go only to your
local LLM. In the web UI, tick "Read pictures" in Ask mode. `eval --answers` takes `--images` too.

Expect it to be slower and not necessarily better. On the benchmark, where OCR already reads every document
correctly, `--images` didn't improve any answer. Answers took about 3× longer on average, some passport questions
took over 2 minutes, and one request ran for hours before labrador had an overall deadline; it now stops after 5
minutes (`llm_deadline_s`). See
[the answers report](../../evals/answers/REPORT.md#reading-pictures---images-p6).

## Masking

IDs, card numbers and other long codes print masked (`•••••02C3`) unless you pass `--reveal`. The status line says
`--reveal to show` when something was hidden.

## Privacy

- The LLM URL must resolve to this machine (loopback). Anything else is refused. `--allow-remote-llm` overrides that,
  prints a warning on every run, and sends your question and file excerpts to that server.
- Ollama can list cloud models that run off-machine. Set `OLLAMA_NO_CLOUD=1`; `ask` warns when the runtime lists a
  `-cloud` model.
- The model has no tools, and labrador never opens a path it produces. Source text is wrapped in delimiters and the
  model is told to ignore instructions in it, which reduces prompt-injection risk but doesn't remove it.
- Nothing is logged or cached: no question history, no prompt dumps.

## Context length

Ollama sets its own context length, not `--ctx`. With the MLX runner and `OLLAMA_CONTEXT_LENGTH=4096`, an
~8,000-token prompt was not truncated, and a per-request context setting had no visible effect. Still set
`OLLAMA_CONTEXT_LENGTH` to the same value as `--ctx` (default 4096), because other runners and builds may truncate
silently. labrador keeps its own token budget either way and warns when it drops or cuts a source to fit.

## Try it without a model

```bash
labrador ask "dog policy" --llm-url fake
```

`fake` returns a canned answer, so you can see the layout. Set `LABRADOR_LLM_URL=fake` to make it the default.
