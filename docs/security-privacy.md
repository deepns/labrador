# Security and privacy

labrador indexes private files, so this page says what it protects, how, and what it does not. For the reasoning
behind the `ask` controls see the [Ask design](design/ask.md#security-and-privacy); to report a problem see
[SECURITY.md](../SECURITY.md).

## Status

| Part | State |
|---|---|
| Read-only source folder, private index permissions, loopback-only web UI with Host/Origin checks and CSP | Merged |
| Loopback-only LLM client (`labrador/llm.py`) | Merged |
| Answer checks and masking (`labrador/answer.py`) and `labrador ask` (CLI) | Merged |
| Ask mode in the web UI | Merged |
| `labrador search` and the web search results | Show snippets **unmasked** |

Masking exists only inside `ask`. Whether it should apply to `search` too is undecided.

## What stays on your machine

- Embedding runs locally. The only network use is the one-time model download from Hugging Face (see
  [Installation](installation.md)); after that nothing leaves your machine.
- There is no telemetry, no account and no cloud service.
- The LLM client (for `ask`) talks only to a server on this machine, normally Ollama on `127.0.0.1`.

## Your files are read-only

labrador only reads the folder you point it at. Every write (database, vectors, thumbnails) goes to the index
directory, `~/.labrador/indexes/<folder>-<hash>/`, or under `LABRADOR_HOME` if set.

## The index

The index contains the text of your files (for search snippets), their paths, vectors and thumbnails. Treat it as
sensitive as the files themselves.

- Index directories are created `0700` and `index.db*` (including the `-wal` and `-shm` files) `0600`, so other
  local users can't read them.
- It is not encrypted. Anyone with your account, or a backup of your home folder, can read it. Use FileVault.
- Delete the index directory to remove it. The source folder is untouched.

## The web UI

`labrador serve` binds to `127.0.0.1`. In `labrador/web.py`:

- **Host allow-list.** Only `127.0.0.1` and `localhost` are accepted, which blocks DNS rebinding.
- **Origin check.** A POST (such as `/reveal/{fid}`, which opens a file or shows it in Finder) whose `Origin`
  doesn't match the Host is refused, so another website can't trigger it. A request with no `Origin` header, like
  `curl`, is allowed.
- **Headers on every response.** `Content-Security-Policy: default-src 'self'; img-src 'self'; connect-src 'self';
  frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, and
  `Cache-Control: no-store` unless a route sets its own. The CSP also applies to indexed `.html` files opened
  from the UI, so they can't run scripts on labrador's origin.
- **Ask is plain text and JSON-only.** `POST /api/ask` requires `Content-Type: application/json` (415 otherwise),
  which also forces a CORS preflight for cross-site callers, on top of the Origin check. Answers and sources are
  rendered with `textContent`, never `innerHTML`, and identifiers are masked on the server; the page only swaps in
  the raw value when you click it.
- **Only indexed files.** `/file/{fid}` and `/reveal/{fid}` take a file ID from the index, never a path.
- **No LAN exposure by default.** `serve` refuses a non-loopback `--host` unless you also pass `--allow-lan`.
  That exposes your whole index to the network, with no login. Don't, unless the network is yours alone.

There is no authentication: any program running as you on this machine can use the UI.

## The local LLM (`ask`)

- **Loopback only.** `llm.require_loopback` resolves the LLM URL's host and refuses it unless every resolved
  address is loopback, so a hostname that points off the machine is caught too.
- **Opt-out is loud.** `--allow-remote-llm` (setting `allow_remote_llm`) skips the check and prints a warning on
  every run; your question and file excerpts then go to that server.
- **No proxies, no redirects.** The client ignores `HTTP_PROXY` and similar variables and doesn't follow redirects,
  so a request can't be routed off the machine behind your back.
- **Runtime-side cloud features are outside labrador.** Ollama can offer cloud models and web search. Set
  `OLLAMA_NO_CLOUD=1` to turn them off.
- **No tools.** The model can't run commands, fetch URLs or open files. It returns text only.

## Answer checks and masking

A file in your folder can contain instructions or false facts aimed at the model. labrador can't stop a model
reading them, so it limits the damage:

- Source text is wrapped in delimiters containing a per-request nonce, with any copy of the nonce stripped from the
  text. This reduces injection risk but doesn't guarantee against it.
- Code, not the model, checks the answer: citation numbers must exist; IDs and dates must appear verbatim in a
  cited source; passport MRZ check digits are validated. Confidence comes from these checks only.
- Identifiers (MRZ lines, long digit runs, Luhn-valid card numbers, SSN shapes) are masked down to their last 4
  characters, so shoulder-surfing and terminal scrollback show less. File names, pages and dates are never masked.
- The model's output is plain text. Nothing it writes is opened, and citations map to labrador's own path
  metadata.

Masking is not a security boundary against someone with access to the index. A planted wrong answer that passes
the checks is still possible: read the sources shown beside each answer.

## Residual risks

- A malicious file can still produce a wrong answer. The checks catch altered IDs and dates, not a false statement.
- Anything with your user account can read the index and use the UI.
- Snippets from `search` are unmasked, for now.
- Backups, Spotlight and Time Machine copy the index like any other file.
