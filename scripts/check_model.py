"""Phase 1 smoke test: is EmbeddingGemma 2 running correctly on this Mac?

    uv run python scripts/check_model.py            # float32 on MPS
    uv run python scripts/check_model.py --dtype bfloat16

Checks: device, dtype, load time, text retrieval sanity, cross-modal (text <-> image)
sanity, Matryoshka truncation, NaN guard, and rough throughput.
"""

from __future__ import annotations

import argparse
import platform
import time

import numpy as np
import torch
from PIL import Image, ImageDraw
from sentence_transformers import SentenceTransformer


def drawn_images():
    sun = Image.new("RGB", (448, 448), (120, 180, 240))
    d = ImageDraw.Draw(sun)
    d.rectangle([0, 300, 448, 448], fill=(230, 210, 150))       # sand
    d.rectangle([0, 250, 448, 300], fill=(30, 100, 190))         # sea
    d.ellipse([300, 40, 400, 140], fill=(255, 220, 60))          # sun
    chart = Image.new("RGB", (448, 448), "white")
    d = ImageDraw.Draw(chart)
    for i, h in enumerate([80, 140, 200, 300]):
        d.rectangle([40 + i * 100, 400 - h, 110 + i * 100, 400], fill=(40, 90, 160))
    d.line([(30, 400), (430, 400)], fill="black", width=3)
    return {"beach": sun, "chart": chart}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="google/embeddinggemma-2")
    ap.add_argument("--dtype", default="float32", choices=["float32", "bfloat16"])
    ap.add_argument("--device", default="mps" if torch.backends.mps.is_available() else "cpu")
    a = ap.parse_args()

    print(f"macOS {platform.mac_ver()[0]}  {platform.machine()}  torch {torch.__version__}  "
          f"MPS available={torch.backends.mps.is_available()}")

    t = time.time()
    model = SentenceTransformer(a.model, device=a.device,
                                model_kwargs={"torch_dtype": getattr(torch, a.dtype)},
                                config_kwargs={"audio_config": None})
    print(f"loaded in {time.time()-t:.1f}s on {model.device} as {model.dtype}; "
          f"params={sum(p.numel() for p in model.parameters())/1e6:.0f}M")

    # 1. Text retrieval (model-card example)
    q = model.encode("What causes the northern lights?", prompt_name="SearchQuery")
    docs = ["title: none | text: The northern lights are caused by charged particles from the sun.",
            "title: none | text: Banana bread needs very ripe bananas."]
    d = model.encode(docs, prompt="")
    sims = model.similarity(q, d)[0].tolist()
    print(f"text   : aurora doc {sims[0]:.3f}  vs banana doc {sims[1]:.3f}  ->",
          "OK" if sims[0] > sims[1] else "UNEXPECTED")

    # 2. Cross-modal: text query vs images
    imgs = drawn_images()
    iv = model.encode([{"image": im} for im in imgs.values()])
    for query, want in [("a sunny beach by the sea", "beach"), ("a bar chart", "chart")]:
        qv = model.encode(query, prompt_name="SearchQuery")
        s = dict(zip(imgs, model.similarity(qv, iv)[0].tolist()))
        best = max(s, key=s.get)
        print(f"image  : '{query}' -> {best}  {', '.join(f'{k}={v:.3f}' for k, v in s.items())}  ->",
              "OK" if best == want else "UNEXPECTED")
    print("         (note how text->image cosines sit lower than text->text: the modality gap)")

    # 3. Matryoshka
    for dim in (512, 256):
        qv = model.encode("What causes the northern lights?", prompt_name="SearchQuery",
                          truncate_dim=dim, normalize_embeddings=True)
        dv = model.encode(docs, prompt="", truncate_dim=dim, normalize_embeddings=True)
        print(f"MRL {dim}: shape={qv.shape} norm={np.linalg.norm(qv):.3f} sims={model.similarity(qv, dv)[0].tolist()}")

    # 4. NaN guard + throughput
    batch = [f"title: none | text: sample sentence number {i} about storage systems." for i in range(64)]
    t = time.time(); e = model.encode(batch, batch_size=16, prompt=""); dt = time.time() - t
    print(f"finite={np.isfinite(e).all()}  text throughput ~{len(batch)/dt:.0f} chunks/s")
    t = time.time(); model.encode([{"image": imgs['beach']}] * 8, batch_size=4); dt = time.time() - t
    print(f"image throughput ~{8/dt:.1f} images/s (280 vision tokens)")


if __name__ == "__main__":
    main()
