# FAQ

## Does anything leave my machine?

No, apart from the one-time model download from Hugging Face. Searching, the web UI and the local LLM used by `ask`
all run on your machine; see [Security and privacy](security-privacy.md).

## Will labrador change or delete my files?

No. The source folder is read-only to labrador. Everything it writes goes to the index directory.

## Where is my index, and how do I remove it?

Under `~/.labrador/indexes/<folder>-<hash>/` (root set by `LABRADOR_HOME`). Delete that directory. See
[Installation](installation.md#where-indexes-live).

## Do I need to download a model?

Yes, about 1.5 GB, once. To try the plumbing without it, add `--backend fake` to a command. Its results say
nothing about search quality.

## Which files can it index?

Text and documents, PDFs, images and photos (with OCR). The extension sets live in `labrador/config.py`. OCR needs
the `mac` extra on a Mac; see [Installation](installation.md).

## Why does a text query find images?

EmbeddingGemma 2 puts text and images in one vector space. Text-to-image scores run lower than text-to-text, so
labrador ranks each kind separately before merging them with keyword (BM25) results.

## Search misses a file I know is there

Check `labrador stats` to see whether it was indexed. Re-run `labrador index` on the folder; it is incremental. If
you changed embedding options such as `--dim`, rebuild with `labrador index <folder> --rebuild`.

## Why "index with --rebuild" after some changes?

An index records the model and dimension it was built with and refuses a mismatch. Changes to document
formatting, vision token budgets or dtype aren't covered by that check, so rebuild so old and new vectors never
share an index.

## Can I run it on Linux or Intel?

The supported setup is an Apple Silicon Mac. Other platforms are untested.

## Can I put the web UI on my network?

Not by default. `labrador serve` refuses a non-loopback `--host` unless you pass `--allow-lan`, which exposes
the index with no login. See [Security and privacy](security-privacy.md#the-web-ui).

## What about `labrador ask`?

It answers questions from your files with a local LLM (Ollama by default), with numbered sources, checks done in
code and IDs masked unless you pass `--reveal`. See [Asking questions](usage/asking.md).

## Why are search snippets not masked?

Masking of IDs and card numbers is part of `ask`. `labrador search` still shows raw text; see
[Security and privacy](security-privacy.md#status).

## I found a security problem

See [SECURITY.md](../SECURITY.md).
