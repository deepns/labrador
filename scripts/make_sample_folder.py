"""Create a small mixed-media test folder so you can try labrador before pointing it at real files.

    uv run python scripts/make_sample_folder.py ~/labrador-sample

Makes: markdown/text notes, a .docx, rendered images with text (receipt, error screenshot),
pure pictures (sunset, chart), a text PDF with embedded figures, and an image-only
"scanned" PDF that can only be found through OCR. Add a few of your own photos to it too:
the model recognises real photos far better than these drawn ones.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def font(size: int):
    for name in ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "DejaVuSans.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def mono(size: int):
    for name in ("/System/Library/Fonts/Menlo.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return font(size)


NOTES = {
    "notes/kubernetes-networking.md": """# Kubernetes networking cheat sheet

Every pod gets its own IP address. Pods on different nodes reach each other directly through the
CNI plugin (Calico, Cilium, Flannel) without NAT. A Service gives a stable virtual IP in front of a
changing set of pods; kube-proxy or eBPF programs the forwarding rules.

## Debugging
- `kubectl exec -it pod -- curl svc-name:8080` to test service DNS.
- NetworkPolicies are default-allow until the first policy selects a pod; then it's default-deny.
- If DNS fails, check CoreDNS pods and the ndots setting in resolv.conf.
""",
    "recipes/banana-bread.txt": """Grandma's banana bread

3 very ripe bananas, mashed (the browner the better)
1/3 cup melted butter, 3/4 cup sugar, 1 egg, 1 tsp vanilla
1 tsp baking soda, pinch of salt, 1.5 cups flour, handful of walnuts

Mix butter into the mashed bananas, then sugar, egg and vanilla. Stir in soda and salt, then flour.
Bake at 350F (175C) for about 60 minutes until a toothpick comes out clean. Cool before slicing.
""",
    "travel/kyoto-trip-notes.md": """# Kyoto, three days in April

Day 1: Fushimi Inari early in the morning before the crowds; thousands of vermilion torii gates up the mountain.
Day 2: Arashiyama bamboo grove, Tenryu-ji garden, then the monkey park. Evening walk in Gion.
Day 3: Kinkaku-ji (the golden pavilion), Ryoan-ji rock garden, Nishiki market for lunch.

Buy an ICOCA card for buses. Cherry blossoms peak first week of April along the Philosopher's Path.
""",
    "work/oncall-handbook.html": """<html><body><h1>On-call handbook</h1>
<p>When the pager fires, acknowledge within 5 minutes. Check the dashboard for error rate and p99 latency.</p>
<p>For a <b>503 Service Unavailable</b> spike, first look at upstream health checks and the load balancer.</p>
<p>Escalate to the secondary after 20 minutes without mitigation. Write the incident timeline as you go.</p>
</body></html>""",
}

DOCX_PARAS = [
    "Q3 planning meeting – notes",
    "Attendees: platform team leads, product, finance.",
    "Decision: we will hire two more engineers for the retrieval team in Q3, one senior and one new grad.",
    "Decision: move the nightly ingestion batch from 02:00 to 04:00 to avoid the backup window.",
    "Open question: whether to adopt a multimodal embedding model for screenshots and scanned documents.",
    "Action items: draft the hiring plan (owner: lead), benchmark embedding models on our eval set (owner: ML).",
]

LEASE = """Maple Court Apartments
Tenant Notice - Lease Addendum

Dear Resident,

This addendum updates section 14 of your lease regarding animals.
Cats and dogs under 40 pounds are permitted with a refundable pet
deposit of $400 and a monthly pet rent of $35. Aggressive breeds,
reptiles and birds of prey are not allowed. Service animals are
always welcome and are exempt from deposits and pet rent.

Rent is due on the first of each month. A late fee of $75 applies
after the fifth day.

Sincerely,
Property Management Office"""


def receipt(path: Path):
    im = Image.new("RGB", (520, 760), "white")
    d = ImageDraw.Draw(im)
    f, b = font(24), font(30)
    y = 30
    for line, ff in [("BLUE DOOR CAFE", b), ("212 Pike Street, Seattle", f), ("", f),
                     ("Oat milk latte        5.25", f), ("Almond croissant      4.50", f),
                     ("Cold brew            4.00", f), ("", f), ("Subtotal             13.75", f),
                     ("Tax                   1.00", f), ("TOTAL               $14.75", b), ("", f),
                     ("VISA ****  APPROVED", f), ("Thank you! Come again", f)]:
        d.text((40, y), line, fill="black", font=ff)
        y += 50
    im.save(path)


def error_screenshot(path: Path):
    im = Image.new("RGB", (1100, 420), (30, 30, 34))
    d = ImageDraw.Draw(im)
    f = mono(22)
    lines = ["$ curl -i https://api.internal/v2/orders", "HTTP/1.1 503 Service Unavailable",
             "content-type: text/plain", "", "upstream connect error or disconnect/reset before headers.",
             "reset reason: connection timeout", "", "ERROR [orders-gateway] request_id=8f3a21 upstream timeout after 15000ms"]
    for i, line in enumerate(lines):
        d.text((30, 30 + i * 44), line, fill=(255, 110, 110) if "ERROR" in line or "503" in line else (220, 220, 220), font=f)
    im.save(path)


def sunset(path: Path):
    W, H = 1200, 800
    im = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(im)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=(int(255 - 60 * t), int(140 - 80 * t), int(60 + 90 * t)))
    d.ellipse([480, 330, 720, 570], fill=(255, 210, 90))
    d.polygon([(0, 800), (250, 380), (520, 800)], fill=(60, 40, 70))
    d.polygon([(300, 800), (650, 300), (1000, 800)], fill=(45, 30, 60))
    d.polygon([(750, 800), (1020, 420), (1200, 650), (1200, 800)], fill=(70, 50, 80))
    d.polygon([(560, 390), (650, 300), (735, 400), (690, 380), (650, 410), (610, 380)], fill=(240, 240, 250))
    im.save(path)


def bar_chart(path: Path, title="Quarterly revenue 2026 ($M)"):
    im = Image.new("RGB", (1000, 650), "white")
    d = ImageDraw.Draw(im)
    d.text((60, 25), title, fill="black", font=font(30))
    vals = [("Q1", 42), ("Q2", 55), ("Q3", 71), ("Q4", 88)]
    for i, (q, v) in enumerate(vals):
        x = 120 + i * 200
        d.rectangle([x, 580 - v * 5, x + 120, 580], fill=(47, 93, 80))
        d.text((x + 40, 590), q, fill="black", font=font(24))
        d.text((x + 35, 545 - v * 5), str(v), fill="black", font=font(24))
    d.line([(90, 580), (950, 580)], fill="black", width=2)
    im.save(path)


def pie_chart(path: Path):
    im = Image.new("RGB", (900, 650), "white")
    d = ImageDraw.Draw(im)
    d.text((40, 20), "Market share by region", fill="black", font=font(30))
    parts = [("North America", 45, (47, 93, 80)), ("Europe", 30, (200, 120, 60)), ("Asia Pacific", 25, (90, 120, 190))]
    start = -90
    for i, (name, pct, col) in enumerate(parts):
        end = start + pct * 3.6
        d.pieslice([60, 100, 560, 600], start, end, fill=col)
        d.rectangle([620, 200 + i * 60, 650, 230 + i * 60], fill=col)
        d.text((665, 200 + i * 60), f"{name} {pct}%", fill="black", font=font(24))
        start = end
    im.save(path)


def text_image(text: str, path: Path):
    im = Image.new("RGB", (1275, 1650), "white")      # US letter at 150 dpi
    d = ImageDraw.Draw(im)
    d.multiline_text((110, 120), text, fill=(20, 20, 20), font=font(30), spacing=16)
    im = im.rotate(0.6, fillcolor="white")             # a little skew, like a real scan
    return im


def report_pdf(path: Path, figs: Path):
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=letter)
    c.setTitle("Acme Annual Report 2026")

    def para(lines, y):
        for ln in lines:
            c.drawString(1 * inch, y, ln)
            y -= 16
        return y

    c.setFont("Helvetica-Bold", 20); c.drawString(1 * inch, 10 * inch, "Acme Corp - Annual Report 2026")
    c.setFont("Helvetica", 11)
    para(["Revenue grew every quarter this year, finishing at $88M in Q4, up 2.1x from Q1.",
          "Growth came mostly from the storage analytics product and new enterprise contracts.",
          "Operating margin improved to 18% as cloud hosting costs fell after the migration."], 9.4 * inch)
    c.drawImage(str(figs / "fig_revenue.png"), 1 * inch, 4 * inch, width=6 * inch, height=3.9 * inch)
    c.drawString(1 * inch, 3.7 * inch, "Figure 1. Revenue by quarter.")
    c.showPage()

    c.setFont("Helvetica-Bold", 16); c.drawString(1 * inch, 10 * inch, "Regional performance")
    c.setFont("Helvetica", 11)
    para(["North America remains the largest region. Europe grew fastest after the Frankfurt launch.",
          "Asia Pacific is a priority for next year, with a new office opening in Bengaluru."], 9.5 * inch)
    c.drawImage(str(figs / "fig_regions.png"), 1 * inch, 4.5 * inch, width=6 * inch, height=4.3 * inch)
    c.showPage()

    c.setFont("Helvetica-Bold", 16); c.drawString(1 * inch, 10 * inch, "Facilities and risks")
    c.setFont("Helvetica", 11)
    para(["Our headquarters lease in Seattle runs until 2029 with an option to renew for five years.",
          "Key risks: customer concentration (top 5 customers are 31% of revenue), currency exposure",
          "in Europe, and hiring competition for machine learning engineers."], 9.5 * inch)
    c.showPage()
    c.save()


def main(out: Path):
    out = out.expanduser()
    for rel, body in NOTES.items():
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)

    try:
        import docx
        doc = docx.Document()
        doc.add_heading(DOCX_PARAS[0], 1)
        for para in DOCX_PARAS[1:]:
            doc.add_paragraph(para)
        (out / "work").mkdir(parents=True, exist_ok=True)
        doc.save(out / "work/q3-planning-meeting.docx")
    except ImportError:
        print("python-docx not installed: skipping the .docx sample")

    img = out / "images"
    img.mkdir(parents=True, exist_ok=True)
    receipt(img / "IMG_2041.png")             # deliberately meaningless names: content must carry the search
    error_screenshot(img / "Screenshot 2026-09-12 at 10.41.22.png")
    sunset(img / "wallpaper.png")
    bar_chart(img / "chart1.png")

    pdfs = out / "pdfs"
    pdfs.mkdir(parents=True, exist_ok=True)
    figs = out / ".figs"
    figs.mkdir(exist_ok=True)
    bar_chart(figs / "fig_revenue.png", "Revenue by quarter ($M)")
    pie_chart(figs / "fig_regions.png")
    try:
        report_pdf(pdfs / "annual-report-2026.pdf", figs)
    except ImportError:
        print("reportlab not installed: skipping the text PDF (uv pip install reportlab)")

    scan = text_image(LEASE, pdfs / "scan0007.pdf")
    scan.save(pdfs / "scan0007.pdf", "PDF", resolution=150)   # image-only PDF: found only via OCR / vision

    print(f"Sample folder ready: {out}")
    for p in sorted(out.rglob("*")):
        if p.is_file() and ".figs" not in p.parts:
            print("  ", p.relative_to(out))


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "~/labrador-sample"))
