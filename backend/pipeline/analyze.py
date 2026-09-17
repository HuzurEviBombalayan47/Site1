"""Orchestrates transcript -> LLM analysis -> asset search -> timeline."""
import random

from providers import llm, media
from pipeline import timeline as T
from pipeline.sfx import sfx_names

KIND_MAP = {"image": "image", "video": "video", "gif": "gif", "meme": "gif"}


def _fetch_asset(seg: dict):
    kind = KIND_MAP.get(seg.get("visual_type", "image"), "image")
    query = (seg.get("search_query") or seg.get("topic") or "").strip()
    tries = [(kind, query)]
    # fallbacks
    entities = seg.get("entities") or []
    if entities:
        tries.append(("image", " ".join(entities[:2])))
    tries.append(("image", seg.get("topic") or query))
    for k, q in tries:
        if not q:
            continue
        try:
            results = media.search(k, q)
        except Exception:
            results = []
        if results:
            return results[0]
    return None


def _pick_effect(seg: dict, mode: str):
    eff = seg.get("effect", "kenburns")
    if seg.get("emphasis"):
        if mode == "shitpost":
            return random.choice(["shake", "zoom_in", "shake"])
        if mode == "fast":
            return random.choice(["zoom_in", "zoom_out", "pan_right"])
    return eff


def _fallback_segments(words: list, duration: float, mode: str):
    """Naive segmentation if the LLM fails: ~3s chunks using key words as query."""
    segs = []
    chunk = 3.0
    t = 0.0
    idx = 0
    while t < duration:
        end = min(duration, t + chunk)
        block = [w for w in words if w["start"] >= t and w["start"] < end]
        text = " ".join(w["text"] for w in block)
        # naive query = longest words
        kws = sorted({w["text"].strip(".,!?").lower() for w in block if len(w["text"]) > 4}, key=len, reverse=True)
        query = " ".join(kws[:2]) or (text[:40] if text else "abstract background")
        segs.append(
            {
                "start": t,
                "end": end,
                "text": text,
                "topic": text[:60],
                "entities": kws[:3],
                "visual_type": "image",
                "search_query": query,
                "effect": "kenburns" if idx % 2 == 0 else "zoom_in",
                "needs_sfx": False,
                "sfx": None,
                "emphasis": False,
            }
        )
        t = end
        idx += 1
    return segs


def build_timeline(words: list, duration: float, mode: str, fmt: str, log=lambda m: None) -> dict:
    canvas = T.FORMATS.get(fmt, T.FORMATS["youtube"])
    log("Konular belirleniyor...")
    used_llm = True
    try:
        segments = llm.analyze(words, duration, mode, sfx_names())
    except Exception as e:
        used_llm = False
        log(f"AI analizi yedeğe geçti ({str(e)[:60]})")
        segments = _fallback_segments(words, duration, mode)

    segments = T.normalize_segments(segments, duration)

    log("Görseller aranıyor...")
    visuals = []
    sfx = []
    for seg in segments:
        asset = _fetch_asset(seg)
        effect = _pick_effect(seg, mode)
        visuals.append(T.make_clip(seg, asset, effect))
        if seg.get("needs_sfx") and seg.get("sfx") in sfx_names():
            sfx.append(T.make_sfx(seg))

    log("Altyazılar oluşturuluyor...")
    captions = T.build_caption_lines(words)

    return {
        "duration": round(duration, 3),
        "canvas": {"w": canvas["w"], "h": canvas["h"], "format": fmt, "label": canvas["label"]},
        "visuals": visuals,
        "captions": captions,
        "sfx": sfx,
        "music": [],
        "used_llm": used_llm,
    }
