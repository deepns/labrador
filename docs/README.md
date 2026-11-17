# labrador docs

Start with the [top-level README](../README.md) for what labrador is and how the pipeline fits together.

## Page map

- [Installation](installation.md): install with uv, extras, the model download, where indexes live
- [Quick start](usage/quickstart.md): index a sample folder, search it, open the web UI
- [Indexing](usage/indexing.md): what gets indexed, re-runs, `--rebuild`, options, `watch` and `stats`
- [Searching](usage/searching.md): `labrador search`, filters, how ranking works, writing good queries
- [Web UI](usage/web-ui.md): `labrador serve`, Search and Ask modes, filters, Open and Show in Finder
- [Asking questions](usage/asking.md): `labrador ask`, answers from a local LLM, masking and privacy
- [Evaluating](usage/evaluating.md): `labrador eval`, query files, hit@1, hit@5, MRR@10, the benchmark
- [FAQ](faq.md): common questions on privacy, indexes and search
- [Security and privacy](security-privacy.md): what stays local, the controls in place and their limits
- [CLI reference](reference/cli.md): every command and flag, generated from the parser
- [Configuration](reference/configuration.md): settings, environment variables, the index layout
- [Ask design](design/ask.md): design and rollout plan for `labrador ask`
- [Timings design](design/observability.md): timings and `--trace` for search and ask
