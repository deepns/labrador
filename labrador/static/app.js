const LABEL = { text: "text", image: "image", image_ocr: "text in image", pdf_text: "PDF text", pdf_page: "PDF page",
                pdf_ocr: "scanned page", pdf_image: "embedded image", pdf_image_ocr: "text in embedded image" };
let only = "", timer = null, seq = 0, mode = "search", abort = null;
const $ = (id) => document.getElementById(id);
const esc = (s) => s.replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
function highlight(text, q) {
  const words = q.toLowerCase().match(/[\p{L}\p{N}]{3,}/gu) || [];
  let html = esc(text.slice(0, 700));
  for (const w of words) html = html.replace(new RegExp(`(${w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi"), "<mark>$1</mark>");
  return html;
}
async function run() {
  const q = $("q").value.trim(), my = ++seq;
  if (!q) { $("results").innerHTML = ""; $("empty").style.display = ""; return; }
  const t0 = performance.now();
  const r = await fetch(`/api/search?k=24&q=${encodeURIComponent(q)}&only=${only}`);
  const hits = await r.json();
  if (my !== seq) return;
  $("stat").textContent = `${hits.length} results · ${Math.round(performance.now() - t0)} ms`;
  $("empty").style.display = hits.length ? "none" : "";
  if (!hits.length) $("empty").textContent = "Nothing found.";
  $("results").innerHTML = hits.map(h => {
    const name = h.path.split("/").pop();
    const page = h.page ? ` · page ${h.page}` : "";
    const open = `/file/${h.file_id}${h.page ? "#page=" + h.page : ""}`;
    const thumb = h.media ? `<div class="thumb" data-src="/media/${h.media}"><img loading="lazy" src="/media/${h.media}" alt=""></div>` : "";
    const via = h.matched.filter(k => k !== h.kind).map(k => LABEL[k] || k);
    return `<div class="card">${thumb}<div class="body">
      <div class="meta"><span class="kind">${LABEL[h.kind] || h.kind}</span><span>${page.slice(3)}</span>
        <span class="push" title="cosine similarity">${h.cosine.toFixed(3)}</span></div>
      <div class="name" title="${esc(h.path)}">${esc(name)}</div>
      ${h.snippet ? `<div class="snip">${highlight(h.snippet, q)}</div>` : ""}
      ${via.length ? `<div class="meta">also matched: ${via.join(", ")}</div>` : ""}
      <div class="actions"><a href="${open}" target="_blank">Open${page}</a>
        <a data-fid="${h.file_id}">Show in Finder</a></div></div></div>`;
  }).join("");
}
$("q").addEventListener("input", () => { clearTimeout(timer); if (mode === "search") timer = setTimeout(run, 250); });
$("q").addEventListener("keydown", e => { if (e.key === "Enter" && mode === "ask") ask(); });
function setMode(m) {
  mode = m; document.body.classList.toggle("ask", m === "ask");
  $("m-search").setAttribute("aria-pressed", m === "search"); $("m-ask").setAttribute("aria-pressed", m === "ask");
  $("q").placeholder = m === "ask" ? "Ask a question about your files, then press Enter…" : "Describe what you're looking for…";
  $("answer").hidden = m !== "ask"; $("results").hidden = m === "ask"; $("empty").hidden = m === "ask";
  if (abort) abort.abort();
  if (m === "search") run();
}
$("m-search").addEventListener("click", () => setMode("search"));
$("m-ask").addEventListener("click", () => setMode("ask"));

// Ask mode. Everything from the model or the server is built with createElement/textContent, never innerHTML.
const el = (tag, text, cls) => { const n = document.createElement(tag); if (text) n.textContent = text; if (cls) n.className = cls; return n; };
function seg(s) {                                    // a string, or {mask, raw} that toggles on click
  if (typeof s === "string") return document.createTextNode(s);
  const n = el("span", s.mask, "masked"); let shown = false;
  n.title = "click to show or hide"; n.addEventListener("click", () => { shown = !shown; n.textContent = shown ? s.raw : s.mask; });
  return n;
}
function statusLine(c, masked) {                     // port of cli._status_line
  const out = el("div"), parts = [];
  if (c.refused) { out.textContent = "refused"; return out; }
  if (c.unverified.length) {
    const s = el("span", "✗ unverified: ");
    c.unverified.forEach((t, i) => { if (i) s.append(", "); s.append(seg(t)); });
    parts.push(s);
  } else if (c.citations.length && !c.bad_citations.length) {
    const cites = c.citations.map(n => `[${n}]`).join(", ");
    parts.push(c.mrz === "invalid" || c.confidence === "low" ? `✗ check the source ${cites}` : `✓ verified against ${cites}`);
  } else parts.push("✗ unverified");
  if (c.bad_citations.length) parts.push(`bad citations: ${c.bad_citations.join(", ")}`);
  if (c.mrz) parts.push("MRZ check digits " + c.mrz.replace("invalid", "INVALID"));
  parts.push(`${c.confidence} confidence`);
  if (masked) parts.push("click a masked value to show it");
  parts.forEach((p, i) => { if (i) out.append(" · "); out.append(p); });
  return out;
}
async function ask() {
  const q = $("q").value.trim(); if (!q) return;
  if (abort) abort.abort();
  abort = new AbortController();
  const box = $("answer"); box.replaceChildren();
  const src = el("div"), warn = el("div"), text = el("div", "", ""), check = el("div");
  text.id = "text"; check.id = "check"; box.append(src, warn, text, check);
  let masked = false, waiting = true;           // waiting: no delta yet
  const status = (m) => { check.replaceChildren(m); };
  status("Searching…");
  try {
    const r = await fetch("/api/ask", { method: "POST", headers: { "content-type": "application/json" },
                                        body: JSON.stringify({ q }), signal: abort.signal });
    if (!r.ok) { status(await r.text()); return; }
    const rd = r.body.getReader(), dec = new TextDecoder(); let buf = "";
    const handle = (e) => {
      if (e.type === "sources") {
        src.replaceChildren(el("h2", "Sources")); const ul = el("ul"); src.append(ul);
        for (const x of e.sources) {
          const li = el("li"), a = el("a", `[${x.n}] ${x.rel_path}${x.page ? " p." + x.page : ""}`);
          a.href = `/file/${x.file_id}${x.page ? "#page=" + x.page : ""}`; a.target = "_blank"; a.rel = "noopener";
          li.append(a, ` (${x.kind}${x.modified ? ", " + x.modified : ""})`); ul.append(li);
        }
        warn.replaceChildren(...e.warnings.map(w => el("div", "warning: " + w, "warn")));
        if (waiting && e.sources.length) status("Writing the answer…");
      } else if (e.type === "delta") {
        if (waiting) { waiting = false; status(""); }
        if ("text" in e) text.append(e.text); else { masked = true; text.append(seg(e)); }
      } else if (e.type === "retry") {
        text.replaceChildren(); masked = false; waiting = true; status(`No answer yet, retrying with “${e.term}”`);
      } else if (e.type === "error") status("error: " + e.message);
      else if (e.type === "done") status(statusLine(e.check, masked || e.check.unverified.some(t => typeof t !== "string")));
    };
    for (;;) {
      const { done, value } = await rd.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const lines = buf.split("\n"); buf = lines.pop();
      for (const l of lines) if (l.trim()) handle(JSON.parse(l));
    }
  } catch (err) { if (err.name !== "AbortError") status("error: " + err.message); }
}
$("chips").addEventListener("click", e => {
  const b = e.target.closest(".chip"); if (!b) return;
  only = b.dataset.only;
  document.querySelectorAll(".chip").forEach(c => c.setAttribute("aria-pressed", c === b));
  run();
});
$("lb").addEventListener("click", () => $("lb").close());
$("results").addEventListener("click", e => {
  const a = e.target.closest("a[data-fid]");
  if (a) { fetch(`/reveal/${a.dataset.fid}`, { method: "POST" }); return; }
  const t = e.target.closest(".thumb"); if (!t) return;
  $("lbimg").src = t.dataset.src; $("lb").showModal();
});
fetch("/api/stats").then(r => r.json()).then(s => {
  const n = Object.values(s.files || {}).reduce((a, b) => a + b, 0);
  const u = Object.values(s.units || {}).reduce((a, b) => a + b, 0);
  $("stat").textContent = `${n} files · ${u} vectors`;
});
