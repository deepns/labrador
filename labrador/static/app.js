const LABEL = { text: "text", image: "image", image_ocr: "text in image", pdf_text: "PDF text", pdf_page: "PDF page",
                pdf_ocr: "scanned page", pdf_image: "embedded image", pdf_image_ocr: "text in embedded image" };
let only = "", timer = null, seq = 0;
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
$("q").addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(run, 250); });
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
