# Web UI

```bash
uv run labrador serve
```

Then browse to <http://127.0.0.1:8765>. `serve` opens the last index you built (or `--index DIR`) and listens on
loopback only, so the page is reachable just from this machine. `--port` picks another port.

## Search mode

Type a description and results update as you type (a quarter-second after you stop). The header shows the index
size (`11 files · 24 vectors`) until the first search, then the result count and time.

The chips under the search box filter by kind, like `search --only`:

| Chip | Shows |
|---|---|
| All | Everything |
| Pictures & pages | Images, PDF page pictures and pictures inside documents (`visual`) |
| Documents | Text chunks from text files and `.docx` (`text`) |
| PDFs | Anything from a PDF (`pdf`) |
| Images | Images and the text read from them (`image`) |

Each card shows:

- a thumbnail for pictures and PDF pages: click it to open a larger view, click again to close it;
- the kind of unit that matched best, the PDF page and the cosine score (compare scores only between cards of the
  same kind, see [Searching](searching.md#how-ranking-works));
- the file name (hover for the full path) and a snippet with your query words highlighted;
- "also matched" when other units of the same group matched too, such as a photo's OCR text;
- **Open**, which opens the original file in a new tab, at the right page for PDFs;
- **Show in Finder**, which reveals the file in Finder (macOS only).

## Ask mode

Flip the toggle in the header from Search to Ask to get an answer from a local LLM instead of a list. It needs the
same local runtime as `labrador ask`; see [Asking questions](asking.md) for setup.

- Type a question and press Enter. Nothing is sent while you type.
- The search results, filter chips and result count are hidden. A search still running when you switch is
  dropped, so it can't fill the page later.
- The sources come first, each linking to the file at the right page, then any warnings (for example sources
  dropped to fit the context), then the answer as it streams in.
- The status line underneath shows the same checks as the terminal: verified citations, MRZ check digits and a
  confidence level. Under it a muted line shows the timings, for example
  `retrieval 0.21 s · answer 4.8 s · first token 1.2 s · 38 tok/s · 3,480 → 182 tokens`; it first shows the
  retrieval time alone, then fills in once the answer is done. A cut-off answer adds a warning line.
- IDs and other long codes show masked (`•••••02C3`). Click one to show it and click again to hide it.

Switching back to Search cancels an answer in progress and runs a fresh search for the text in the box.

`serve` takes the same LLM flags as `ask`:

```bash
uv run labrador serve --model gemma4:e4b --ctx 8192
```

## Privacy and the network

The page only talks to `serve` on your machine, and `serve` only talks to a loopback LLM unless you pass
`--allow-remote-llm`. It rejects requests addressed to any host but `127.0.0.1` or `localhost` (which blocks DNS
rebinding) and POSTs from other sites, sends a strict Content-Security-Policy, and receives questions in a POST
body, so they stay out of browser history and server logs.

`--host` other than loopback is refused unless you also pass `--allow-lan`, because anyone who can reach the port
can read your index. See [Security and privacy](../security-privacy.md) before you do.
