"""Drawing helpers for labrador-bench: fonts, screenshots, receipts, scenes, charts, diagrams, scans."""

from __future__ import annotations

import io
import math
import random

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402

FONT_DIRS = ["/usr/share/fonts/truetype/dejavu/", "/usr/share/fonts/truetype/freefont/",
             "/usr/share/fonts/opentype/inter/", "/System/Library/Fonts/Supplemental/", "/Library/Fonts/"]


def _find(names):
    import os
    for d in FONT_DIRS:
        for n in names:
            if os.path.exists(d + n):
                return d + n
    import subprocess
    for n in names:
        try:
            out = subprocess.run(["fc-match", "-f", "%{file}", n.split(".")[0]], capture_output=True, text=True).stdout
            if out:
                return out
        except Exception:
            pass
    return None


SANS = _find(["DejaVuSans.ttf", "Arial.ttf"])
SANS_B = _find(["DejaVuSans-Bold.ttf", "Arial Bold.ttf"])
MONO = _find(["DejaVuSansMono.ttf", "Menlo.ttc"])
SERIF = _find(["DejaVuSerif.ttf", "Georgia.ttf"])
INDIC = _find(["FreeSans.ttf", "FreeSerif.ttf"])


def font(size, bold=False, kind="sans"):
    path = {"sans": SANS_B if bold else SANS, "mono": MONO, "serif": SERIF, "indic": INDIC}[kind]
    return ImageFont.truetype(path, size) if path else ImageFont.load_default()


# ------------------------------------------------------------------ screenshots

def window(w, h, title, dark=False):
    bg = (32, 33, 36) if dark else (250, 250, 252)
    im = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w, 38], fill=(52, 53, 58) if dark else (232, 232, 236))
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([14 + i * 22, 13, 26 + i * 22, 25], fill=c)
    d.text((w // 2, 19), title, fill=(200, 200, 205) if dark else (90, 90, 95), font=font(15), anchor="mm")
    return im, d


def text_lines(d, x, y, lines, size=20, gap=10, kind="sans", color=(30, 30, 35)):
    for ln in lines:
        if isinstance(ln, tuple):
            txt, opts = ln
        else:
            txt, opts = ln, {}
        f = font(opts.get("size", size), opts.get("bold", False), opts.get("kind", kind))
        d.text((x, y), txt, fill=opts.get("color", color), font=f)
        y += opts.get("size", size) + gap
    return y


def terminal_503():
    im, d = window(1180, 440, "zsh — orders-gateway", dark=True)
    lines = ["$ curl -i https://api.internal/v2/orders", ("HTTP/1.1 503 Service Unavailable", {"color": (255, 110, 110)}),
             "content-type: text/plain", "", "upstream connect error or disconnect/reset before headers.",
             "reset reason: connection timeout", "",
             ("ERROR [orders-gateway] request_id=8f3a21 upstream timeout after 15000ms", {"color": (255, 110, 110)})]
    text_lines(d, 28, 62, lines, size=21, gap=19, kind="mono", color=(222, 222, 222))
    return im


def chat_freeze():
    im, d = window(1100, 560, "Team chat — #release")
    d.rectangle([0, 38, 230, 560], fill=(63, 14, 64))
    text_lines(d, 22, 60, [("Channels", {"bold": True}), "# general", ("# release", {"bold": True}), "# incidents", "# random"],
               size=18, gap=14, color=(235, 225, 235))
    y = 70
    for who, when, msg in [("Marcus Lee", "10:02 AM", ["Heads up: deploy freeze starts Friday 6 pm and runs until",
                                                       "Monday 9 am for the quarter close. Only P1 fixes, with approval."]),
                           ("Priya N", "10:05 AM", ["Thanks! I'll land the OCR changes before Thursday EOD."]),
                           ("Marcus Lee", "10:06 AM", ["Approvers this time: me and Sofia."])]:
        d.rounded_rectangle([260, y, 300, y + 40], 8, fill=(120, 160, 200))
        d.text((316, y), who, fill=(20, 20, 25), font=font(18, True))
        d.text((316 + 12 * len(who), y + 2), when, fill=(120, 120, 125), font=font(15))
        y = text_lines(d, 316, y + 30, msg, size=18, gap=8) + 22
    return im


def calendar_invite():
    im, d = window(980, 520, "Calendar")
    d.rectangle([40, 70, 940, 480], outline=(210, 210, 215), width=2)
    d.rectangle([40, 70, 52, 480], fill=(66, 133, 244))
    text_lines(d, 80, 95, [("Design review: multimodal search", {"size": 30, "bold": True}),
                           "Thursday, October 9  ·  2:00 – 3:00 PM", "Room Cedar (3rd floor) and video link",
                           "", ("Guests", {"bold": True}), "Priya N, Marcus Lee, Sofia Alvarez, Dev Rao",
                           "", "Agenda: architecture, eval results, rollout plan"], size=21, gap=14)
    d.rounded_rectangle([80, 430, 200, 466], 6, fill=(66, 133, 244))
    d.text((140, 448), "Yes", fill="white", font=font(18, True), anchor="mm")
    return im


def boarding_pass():
    im = Image.new("RGB", (1200, 520), (245, 247, 250))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([30, 30, 1170, 490], 24, fill="white", outline=(200, 205, 215), width=2)
    d.rectangle([30, 30, 1170, 110], fill=(18, 78, 120))
    d.text((70, 52), "PACIFIC CREST AIR   ·   BOARDING PASS", fill="white", font=font(30, True))
    text_lines(d, 70, 140, [("SEA  →  SFO", {"size": 54, "bold": True}), "Seattle to San Francisco"], size=24, gap=12)
    cols = [("FLIGHT", "PC 482"), ("DATE", "21 OCT 2026"), ("BOARDING", "7:35 AM"), ("GATE", "N12"), ("SEAT", "14C")]
    for x, (k, v) in zip([70, 230, 450, 640, 780], cols):
        d.text((x, 300), k, fill=(110, 115, 125), font=font(18))
        d.text((x, 328), v, fill=(20, 20, 25), font=font(26, True))
    d.text((70, 420), "PASSENGER  RAO/DEV    CONFIRMATION  K7Q2ZP", fill=(60, 60, 70), font=font(22))
    rnd = random.Random(7)
    for x in range(930, 1130, 6):  # barcode-ish
        if rnd.random() > 0.35:
            d.rectangle([x, 150, x + rnd.choice([2, 3, 4]), 260], fill="black")
    return im


def dashboard():
    fig, ax = plt.subplots(figsize=(9, 3.2), dpi=100)
    t = np.arange(0, 120)
    y = 140 + 12 * np.sin(t / 7) + np.random.default_rng(3).normal(0, 6, len(t))
    y[70:82] += np.array([40, 90, 160, 230, 272, 260, 200, 150, 90, 50, 25, 10])
    ax.plot(t, y, color="#d9534f", lw=2)
    ax.set_ylabel("ms")
    ax.set_xticks([0, 30, 60, 90, 119], ["09:00", "09:30", "10:00", "10:30", "11:00"])
    ax.spines[["top", "right"]].set_visible(False)
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png")
    plt.close(fig)
    chart = Image.open(buf).convert("RGB")
    im, d = window(1000, 640, "Grafana — orders-api")
    tiles = [("p99 latency", "412 ms"), ("Error rate", "0.4 %"), ("Requests/s", "1,240")]
    for i, (k, v) in enumerate(tiles):
        x = 30 + i * 320
        d.rounded_rectangle([x, 60, x + 300, 170], 10, fill="white", outline=(220, 220, 225))
        d.text((x + 20, 76), k, fill=(110, 110, 115), font=font(18))
        d.text((x + 20, 108), v, fill=(217, 83, 79) if i == 0 else (30, 30, 35), font=font(38, True))
    d.text((30, 190), "orders-api p99 latency (last 2 hours)", fill=(30, 30, 35), font=font(20, True))
    im.paste(chart, (50, 225))
    return im


def code_editor():
    im, d = window(1100, 520, "invoice_parser.py — Editor", dark=True)
    d.rectangle([0, 38, 60, 520], fill=(40, 41, 45))
    code = ["from datetime import datetime", "", "def parse_invoice_date(raw: str) -> datetime:",
            '    """Accepts 2026-09-12, 12/09/2026 or Sep 12, 2026."""',
            '    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%b %d, %Y"):', "        try:",
            "            return datetime.strptime(raw.strip(), fmt)", "        except ValueError:",
            "            continue", '    raise ValueError(f"unrecognised date: {raw!r}")']
    for i, ln in enumerate(code):
        d.text((18, 60 + i * 40), str(i + 1), fill=(110, 110, 115), font=font(18, kind="mono"))
        d.text((80, 60 + i * 40), ln, fill=(214, 222, 235), font=font(19, kind="mono"))
    return im


def settings_2fa():
    im, d = window(900, 520, "Account settings")
    text_lines(d, 50, 70, [("Security", {"size": 30, "bold": True}), ""], gap=8)
    rows = [("Two-factor authentication", "On"), ("Authenticator app", "Configured"),
            ("Backup codes", "8 remaining"), ("Trusted devices", "3"), ("Last sign-in", "Oct 3, 2026, Seattle")]
    for i, (k, v) in enumerate(rows):
        y = 140 + i * 66
        d.line([50, y + 52, 850, y + 52], fill=(225, 225, 230))
        d.text((50, y + 12), k, fill=(30, 30, 35), font=font(21))
        d.text((850, y + 12), v, fill=(40, 120, 60) if v == "On" else (90, 90, 95), font=font(21, v == "On"), anchor="ra")
    return im


def order_confirmation():
    im, d = window(1000, 600, "Order confirmation")
    text_lines(d, 60, 70, [("Thanks for your order!", {"size": 34, "bold": True}), "Order #A-58213  ·  placed Oct 11, 2026", ""],
               size=21, gap=12)
    d.rounded_rectangle([60, 200, 940, 420], 10, outline=(220, 220, 225), width=2)
    d.rectangle([80, 220, 260, 400], fill=(150, 105, 70))
    d.rectangle([90, 230, 250, 250], fill=(120, 80, 50))
    text_lines(d, 290, 230, [("Ergonomic standing desk", {"bold": True}), "60 x 30 in, walnut top, black frame",
                             "Qty 1", ("$649.00", {"bold": True})], size=21, gap=14)
    text_lines(d, 60, 450, ["Estimated delivery: Oct 17 – Oct 20", "Shipping to: Rao, Seattle WA"], size=21, gap=12)
    return im


def diwali_card():
    im = Image.new("RGB", (1000, 700), (60, 10, 50))
    d = ImageDraw.Draw(im)
    for i in range(5):
        cx = 150 + i * 175
        d.ellipse([cx - 60, 520, cx + 60, 600], fill=(190, 90, 40))   # clay lamp
        d.polygon([(cx - 12, 525), (cx, 470), (cx + 12, 525)], fill=(255, 200, 60))  # flame
        d.ellipse([cx - 30, 450, cx + 30, 540], outline=(255, 210, 120), width=2)
    rnd = random.Random(5)
    for _ in range(80):
        x, y = rnd.randint(0, 1000), rnd.randint(0, 380)
        d.ellipse([x, y, x + 3, y + 3], fill=(255, 220, 150))
    f = font(64, kind="indic")
    d.text((500, 170), "दिवाली की शुभकामनाएं", fill=(255, 210, 90), font=f, anchor="mm")
    d.text((500, 280), "आपके घर में सुख, शांति और समृद्धि हो", fill=(250, 235, 210), font=font(34, kind="indic"), anchor="mm")
    d.text((500, 650), "— राव परिवार", fill=(250, 235, 210), font=font(28, kind="indic"), anchor="mm")
    return im


# ------------------------------------------------------------------ "photos" of paper

def paper_photo(im, angle, seed, bg=(120, 110, 95)):
    """Make a flat render look like a phone photo of paper: rotation, table background, light falloff, noise."""
    rnd = np.random.default_rng(seed)
    pad = 80
    canvas = Image.new("RGB", (im.width + 2 * pad, im.height + 2 * pad), bg)
    shadow = Image.new("RGB", im.size, (60, 55, 50))
    canvas.paste(shadow, (pad + 10, pad + 12))
    canvas.paste(im, (pad, pad))
    canvas = canvas.rotate(angle, resample=Image.BICUBIC, fillcolor=bg, expand=False)
    a = np.asarray(canvas).astype(np.float32)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    fall = 1 - 0.18 * (((xx - w * 0.4) / w) ** 2 + ((yy - h * 0.35) / h) ** 2)
    a = a * fall[..., None] + rnd.normal(0, 5, a.shape)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))


def receipt(store, address, items, tax, paid, seed, extra=()):
    lines_h = 46
    h = 330 + lines_h * (len(items) + len(extra)) + 140
    im = Image.new("RGB", (560, h), (253, 252, 247))
    d = ImageDraw.Draw(im)
    f, fb, fm = font(24, kind="mono"), font(30, True), font(22, kind="mono")
    d.text((280, 40), store, fill="black", font=fb, anchor="mm")
    d.text((280, 82), address, fill="black", font=fm, anchor="mm")
    y = 140
    sub = 0.0
    for name, price in items:
        d.text((40, y), name, fill="black", font=f)
        d.text((520, y), f"{price:.2f}", fill="black", font=f, anchor="ra")
        sub += price
        y += lines_h
    y += 10
    d.line([40, y, 520, y], fill="black", width=2)
    y += 20
    for k, v in [("SUBTOTAL", sub), ("TAX", tax), ("TOTAL", sub + tax)]:
        d.text((40, y), k, fill="black", font=fb if k == "TOTAL" else f)
        d.text((520, y), f"${v:.2f}" if k == "TOTAL" else f"{v:.2f}", fill="black", font=fb if k == "TOTAL" else f, anchor="ra")
        y += lines_h
    for ln in (paid,) + tuple(extra):
        y += 6
        d.text((280, y + 10), ln, fill="black", font=fm, anchor="mm")
        y += 40
    return paper_photo(im, random.Random(seed).uniform(-5, 5), seed)


def whiteboard():
    im = Image.new("RGB", (1400, 900), (236, 238, 240))
    d = ImageDraw.Draw(im)
    d.rectangle([40, 40, 1360, 860], fill=(250, 250, 250), outline=(170, 170, 175), width=6)
    d.text((700, 90), "Sprint 41 retro", fill=(30, 60, 160), font=font(48, True), anchor="mm")
    cols = [("Went well", (40, 150, 70), ["Faster CI (12 min to 5)", "Great pairing on OCR", "Demo landed"]),
            ("To improve", (200, 60, 50), ["Flaky search tests", "Unclear ownership", "Late design docs"]),
            ("Actions", (30, 60, 160), ["Quarantine flaky tests", "Name a DRI per epic", "Doc before code"])]
    colors = [(255, 236, 140), (255, 190, 200), (190, 230, 255)]
    rnd = random.Random(11)
    for i, (head, col, notes) in enumerate(cols):
        x = 90 + i * 430
        d.text((x + 170, 170), head, fill=col, font=font(36, True), anchor="mm")
        for j, n in enumerate(notes):
            y = 230 + j * 200
            sticky = Image.new("RGB", (340, 160), colors[i])
            sd = ImageDraw.Draw(sticky)
            words = n.split()
            mid = (len(words) + 1) // 2
            sd.text((170, 60), " ".join(words[:mid]), fill=(40, 40, 40), font=font(28), anchor="mm")
            sd.text((170, 102), " ".join(words[mid:]), fill=(40, 40, 40), font=font(28), anchor="mm")
            sticky = sticky.rotate(rnd.uniform(-4, 4), expand=True, fillcolor=(250, 250, 250))
            im.paste(sticky, (x, y))
    return paper_photo(im, -2.5, 12, bg=(90, 85, 80))


# ------------------------------------------------------------------ drawn scenes (synthetic "photos")

def _sky(d, w, h, top, bottom):
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(top[k] * (1 - t) + bottom[k] * t) for k in range(3)))


def scene_sunset():
    W, H = 1200, 800
    im = Image.new("RGB", (W, H)); d = ImageDraw.Draw(im)
    _sky(d, W, H, (255, 120, 60), (90, 50, 120))
    d.ellipse([480, 330, 720, 570], fill=(255, 210, 90))
    d.polygon([(0, 800), (250, 380), (520, 800)], fill=(60, 40, 70))
    d.polygon([(300, 800), (650, 300), (1000, 800)], fill=(45, 30, 60))
    d.polygon([(750, 800), (1020, 420), (1200, 650), (1200, 800)], fill=(70, 50, 80))
    d.polygon([(560, 390), (650, 300), (735, 400), (690, 380), (650, 410), (610, 380)], fill=(240, 240, 250))
    return im


def scene_beach():
    W, H = 1200, 800
    im = Image.new("RGB", (W, H)); d = ImageDraw.Draw(im)
    _sky(d, W, 420, (90, 170, 240), (180, 220, 250))
    d.rectangle([0, 360, W, 520], fill=(30, 110, 180))
    for x in range(0, W, 60):
        d.arc([x, 500, x + 60, 540], 180, 360, fill=(240, 250, 255), width=4)
    d.rectangle([0, 520, W, H], fill=(236, 214, 160))
    d.ellipse([950, 60, 1060, 170], fill=(255, 230, 90))
    d.line([(420, 700), (470, 470)], fill=(90, 70, 50), width=8)
    d.pieslice([300, 400, 640, 640], 180, 360, fill=(220, 60, 60))
    d.rectangle([520, 690, 720, 720], fill=(60, 140, 200))
    for x in (120, 820):
        d.line([(x, 720), (x + 30, 480)], fill=(110, 80, 50), width=14)
        for a in range(0, 360, 60):
            d.line([(x + 30, 480), (x + 30 + 110 * math.cos(math.radians(a)), 480 + 50 * math.sin(math.radians(a)))],
                   fill=(40, 130, 60), width=12)
    return im


def scene_city_night():
    W, H = 1200, 800
    im = Image.new("RGB", (W, H)); d = ImageDraw.Draw(im)
    _sky(d, W, H, (10, 15, 40), (40, 40, 90))
    d.ellipse([950, 90, 1050, 190], fill=(240, 240, 220)); d.ellipse([975, 85, 1065, 175], fill=(14, 20, 48))
    rnd = random.Random(2)
    x = 0
    while x < W:
        w, h = rnd.randint(70, 150), rnd.randint(200, 560)
        d.rectangle([x, H - h, x + w, H], fill=(25, 25, 35))
        for wy in range(H - h + 20, H - 20, 28):
            for wx in range(x + 10, x + w - 14, 22):
                if rnd.random() > 0.45:
                    d.rectangle([wx, wy, wx + 10, wy + 14], fill=(255, 215, 120))
        x += w + rnd.randint(4, 20)
    for _ in range(60):
        sx, sy = rnd.randint(0, W), rnd.randint(0, 260)
        d.point((sx, sy), fill="white")
    return im


def scene_snow_forest():
    W, H = 1200, 800
    im = Image.new("RGB", (W, H)); d = ImageDraw.Draw(im)
    _sky(d, W, 520, (170, 190, 210), (225, 232, 240))
    d.rectangle([0, 520, W, H], fill=(245, 248, 252))
    rnd = random.Random(4)
    for _ in range(26):
        x, base, s = rnd.randint(-40, W), rnd.randint(540, 780), rnd.uniform(0.6, 1.4)
        for k in range(4):
            wdt, top_ = 110 * s * (1 - k * 0.2), base - 90 * s * (k + 1)
            d.polygon([(x - wdt, top_ + 110 * s), (x, top_ - 40 * s), (x + wdt, top_ + 110 * s)], fill=(30, 80, 50))
            d.polygon([(x - wdt * 0.5, top_ + 20 * s), (x, top_ - 40 * s), (x + wdt * 0.5, top_ + 20 * s)], fill=(250, 250, 255))
        d.rectangle([x - 10 * s, base - 10, x + 10 * s, base + 20], fill=(80, 55, 40))
    for _ in range(400):
        sx, sy = rnd.randint(0, W), rnd.randint(0, H)
        d.ellipse([sx, sy, sx + 4, sy + 4], fill="white")
    return im


def scene_red_car():
    W, H = 1200, 800
    im = Image.new("RGB", (W, H)); d = ImageDraw.Draw(im)
    _sky(d, W, 480, (150, 200, 240), (210, 230, 245))
    d.rectangle([0, 480, W, H], fill=(90, 90, 95))
    for x in range(0, W, 120):
        d.rectangle([x, 640, x + 60, 652], fill=(240, 240, 240))
    d.rounded_rectangle([230, 420, 970, 590], 60, fill=(200, 25, 30))
    d.polygon([(380, 425), (470, 300), (760, 300), (860, 425)], fill=(200, 25, 30))
    d.polygon([(410, 420), (485, 320), (600, 320), (600, 420)], fill=(170, 210, 235))
    d.polygon([(620, 420), (620, 320), (745, 320), (825, 420)], fill=(170, 210, 235))
    for cx in (390, 810):
        d.ellipse([cx - 85, 510, cx + 85, 680], fill=(25, 25, 25))
        d.ellipse([cx - 40, 555, cx + 40, 635], fill=(180, 180, 185))
    d.ellipse([925, 460, 965, 490], fill=(255, 240, 180))
    return im


def scene_cake():
    W, H = 1000, 900
    im = Image.new("RGB", (W, H), (255, 240, 245)); d = ImageDraw.Draw(im)
    d.ellipse([150, 700, 850, 820], fill=(230, 230, 235))
    d.rectangle([220, 450, 780, 760], fill=(120, 70, 40))
    d.ellipse([220, 700, 780, 820], fill=(120, 70, 40))
    d.ellipse([220, 390, 780, 510], fill=(110, 200, 120))
    for x in range(240, 780, 70):
        d.ellipse([x, 470, x + 50, 540], fill=(110, 200, 120))
    for i, x in enumerate(range(330, 700, 60)):
        d.rectangle([x, 300, x + 16, 440], fill=[(80, 150, 240), (240, 200, 60), (230, 90, 140)][i % 3])
        d.ellipse([x - 6, 250, x + 22, 300], fill=(255, 190, 40))
        d.ellipse([x + 1, 265, x + 15, 292], fill=(255, 240, 160))
    return im


# ------------------------------------------------------------------ charts (matplotlib)

def chart(kind, path, seed=0):
    rnd = np.random.default_rng(seed)
    fig, ax = plt.subplots(figsize=(8, 5), dpi=110)
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    if kind == "electricity":
        v = [910, 820, 700, 560, 430, 390, 420, 450, 480, 610, 760, 880]
        ax.plot(months, v, marker="o", color="#2f5d50", lw=2.5)
        ax.set_title("Electricity use 2026 (kWh)"); ax.set_ylabel("kWh")
    elif kind == "signups":
        w = np.arange(1, 21)
        ax.plot(w, 900 - 32 * w + rnd.normal(0, 25, len(w)), color="#c0392b", lw=2.5)
        ax.set_xlabel("week"); ax.set_ylabel("count")
    elif kind == "headcount":
        q = ["Q1 25", "Q2 25", "Q3 25", "Q4 25", "Q1 26", "Q2 26", "Q3 26"]
        ax.bar(q, [2, 3, 4, 6, 7, 9, 10], color="#4a78b5")
        ax.set_title("Retrieval team headcount")
    elif kind == "budget":
        ax.pie([38, 18, 9, 20, 15], labels=["Rent", "Food", "Transport", "Savings", "Fun"], autopct="%d%%",
               colors=["#4a78b5", "#e39b3b", "#7d9f4e", "#2f5d50", "#c25b8a"])
        ax.axis("equal")
    elif kind == "scatter":
        lat = rnd.uniform(2, 60, 40); rec = 0.62 + 0.3 * (1 - np.exp(-lat / 15)) + rnd.normal(0, 0.02, 40)
        ax.scatter(lat, rec, color="#6a4c93"); ax.set_xlabel("latency (ms)"); ax.set_ylabel("recall@10")
        ax.set_title("Recall@10 vs latency")
    elif kind == "histogram":
        ax.hist(rnd.lognormal(4.6, 0.45, 3000), bins=50, color="#3b8ea5")
        ax.set_xlabel("ms")
    ax.spines[["top", "right"]].set_visible(False) if kind != "budget" else None
    fig.tight_layout(); fig.savefig(path); plt.close(fig)


def bar_png(labels, values, title, ylabel, color="#2f5d50", size=(7, 4.2)):
    fig, ax = plt.subplots(figsize=size, dpi=120)
    ax.bar(labels, values, color=color)
    ax.set_title(title); ax.set_ylabel(ylabel)
    for i, v in enumerate(values):
        ax.text(i, v, f"{v}", ha="center", va="bottom")
    ax.spines[["top", "right"]].set_visible(False)
    buf = io.BytesIO(); fig.tight_layout(); fig.savefig(buf, format="png"); plt.close(fig)
    return Image.open(buf).convert("RGB")


def score_histograms():
    rnd = np.random.default_rng(9)
    fig, ax = plt.subplots(figsize=(7, 4), dpi=120)
    ax.hist(rnd.normal(0.62, 0.06, 4000), bins=60, alpha=0.6, label="text → text", color="#4a78b5")
    ax.hist(rnd.normal(0.31, 0.05, 4000), bins=60, alpha=0.6, label="text → image", color="#e39b3b")
    ax.set_xlabel("cosine similarity"); ax.set_ylabel("pairs"); ax.legend()
    ax.spines[["top", "right"]].set_visible(False)
    buf = io.BytesIO(); fig.tight_layout(); fig.savefig(buf, format="png"); plt.close(fig)
    return Image.open(buf).convert("RGB")


# ------------------------------------------------------------------ diagrams

def boxes_diagram(boxes, arrows, size=(1200, 700), title=None, diamonds=()):
    """boxes: {key: (cx, cy, label)}; arrows: [(from, to, label)]."""
    im = Image.new("RGB", size, "white"); d = ImageDraw.Draw(im)
    if title:
        d.text((40, 30), title, fill=(30, 30, 35), font=font(30, True))
    BW, BH = 230, 80

    def edge_point(a, b):
        ax_, ay, _ = boxes[a]; bx, by, _ = boxes[b]
        dx, dy = bx - ax_, by - ay
        if abs(dx) * BH > abs(dy) * BW:
            return ax_ + math.copysign(BW / 2, dx), ay + dy * (BW / 2) / abs(dx)
        return ax_ + dx * (BH / 2) / abs(dy), ay + math.copysign(BH / 2, dy)

    for a, b, lab in arrows:
        x1, y1 = edge_point(a, b); x2, y2 = edge_point(b, a)
        d.line([x1, y1, x2, y2], fill=(80, 80, 90), width=3)
        ang = math.atan2(y2 - y1, x2 - x1)
        d.polygon([(x2, y2), (x2 - 16 * math.cos(ang - 0.4), y2 - 16 * math.sin(ang - 0.4)),
                   (x2 - 16 * math.cos(ang + 0.4), y2 - 16 * math.sin(ang + 0.4))], fill=(80, 80, 90))
        if lab:
            d.text(((x1 + x2) / 2 + 8, (y1 + y2) / 2 - 26), lab, fill=(100, 100, 110), font=font(18))
    for k, (cx, cy, label) in boxes.items():
        if k in diamonds:
            d.polygon([(cx - BW / 2, cy), (cx, cy - BH / 1.3), (cx + BW / 2, cy), (cx, cy + BH / 1.3)],
                      fill=(255, 244, 214), outline=(200, 150, 40), width=3)
        else:
            d.rounded_rectangle([cx - BW / 2, cy - BH / 2, cx + BW / 2, cy + BH / 2], 14,
                                fill=(232, 241, 250), outline=(70, 110, 160), width=3)
        lines = label.split("\n")
        for i, ln in enumerate(lines):
            d.text((cx, cy + (i - (len(lines) - 1) / 2) * 26), ln, fill=(25, 25, 30), font=font(21), anchor="mm")
    return im


# ------------------------------------------------------------------ scans

def scanned_page(lines, seed, title_size=34, size=30):
    """A US-letter page at 150 dpi that looks scanned: grey paper, skew, speckle, blur."""
    im = Image.new("RGB", (1275, 1650), (246, 244, 238))
    d = ImageDraw.Draw(im)
    y = 130
    for i, ln in enumerate(lines):
        bold = isinstance(ln, tuple)
        txt = ln[0] if bold else ln
        d.text((120, y), txt, fill=(25, 25, 25), font=font(title_size if bold else size, bold, "serif"))
        y += (title_size if bold else size) + 18
    rnd = np.random.default_rng(seed)
    im = im.rotate(float(rnd.uniform(-1.2, 1.2)), resample=Image.BICUBIC, fillcolor=(246, 244, 238))
    a = np.asarray(im).astype(np.float32) + rnd.normal(0, 7, (1650, 1275, 1))
    specks = rnd.random((1650, 1275)) > 0.9993
    a[specks] = 40
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).convert("L").filter(ImageFilter.GaussianBlur(0.7))
