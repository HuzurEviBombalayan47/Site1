"""Orchestrates transcript -> structured LLM shot-plan -> validated asset resolution -> timeline.

Documentary-grade: contextual matching, query fallback chain, asset validation, sub-shots with
carry-forward, and NEVER a plain solid-color screen (animated typography is the last resort).
"""
import uuid
import requests

from providers import llm, media
from pipeline import timeline as T
from pipeline.sfx import sfx_names

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "ShitpostStudio/1.0 (+render-validator)"})

SUBSHOT_TARGET = 5.0          # seconds per sub-shot
SUBSHOT_MAX = 4               # max sub-shots per semantic block
GENERIC_QUERIES = [
    "cinematic dark background", "documentary footage", "archival old film",
    "moody atmosphere", "abstract light", "city timelapse",
]


def _validate(url: str) -> bool:
    if not url:
        return False
    try:
        r = SESSION.get(url, stream=True, timeout=12, headers={"Range": "bytes=0-4096"})
        ok = r.status_code in (200, 206)
        ct = r.headers.get("Content-Type", "")
        r.close()
        return ok and (ct.startswith("image") or ct.startswith("video") or "octet-stream" in ct or ct == "")
    except Exception:
        return False


def _kinds_for(visual_type: str, style: str):
    if visual_type == "stock_video":
        return ["video", "image"]
    if visual_type == "reaction" and style != "documentary":
        return ["gif", "image"]
    if visual_type == "graphic":
        return []
    return ["image", "video"]


def _cached_search(kind, query, cache, diag):
    key = (kind, query.strip().lower())
    if key in cache:
        return cache[key]
    try:
        diag["searches"] += 1
        results = media.search(kind, query)
    except Exception:
        diag["failed_searches"] += 1
        results = []
    if not results:
        diag["empty_searches"] += 1
    cache[key] = results
    return results


def _resolve_multi(queries, kinds, cache, diag, want, seen_urls):
    """Collect up to `want` distinct validated assets across queries x kinds."""
    found = []
    for q in queries:
        if not q or not q.strip():
            continue
        for kind in kinds:
            results = _cached_search(kind, q, cache, diag)
            for cand in results[:5]:
                url = cand.get("url")
                if not url or url in seen_urls:
                    continue
                if _validate(url):
                    seen_urls.add(url)
                    found.append({**cand, "query_used": q})
                    if len(found) >= want:
                        return found
                    break  # move to next query for variety
    return found


def _effect_for(motion, idx, style, emphasis=False):
    if style == "shitpost" and emphasis:
        return "shake"
    if motion == "pan":
        return "pan_right" if idx % 2 == 0 else "pan_left"
    if motion == "slow_zoom":
        return "zoom_in" if idx % 2 == 0 else "zoom_out"
    if motion == "static":
        return "kenburns"
    return "kenburns" if idx % 2 == 0 else "zoom_in"


def _clip(start, end, seg, asset, effect, source):
    return {
        "id": str(uuid.uuid4()),
        "start": round(start, 3),
        "end": round(end, 3),
        "text": seg.get("narration") or seg.get("text", ""),
        "topic": seg.get("topic", ""),
        "entities": seg.get("entities", []),
        "visual_concept": seg.get("visual_concept", ""),
        "visual_type": (asset["type"] if asset else "text"),
        "planned_type": seg.get("visual_type", "photo"),
        "search_query": (asset.get("query_used") if asset else (seg.get("search_queries") or [""])[0]),
        "search_queries": seg.get("search_queries", []),
        "url": asset["url"] if asset else None,
        "preview": asset.get("preview") if asset else None,
        "provider": asset.get("provider") if asset else None,
        "credit": asset.get("credit") if asset else None,
        "effect": effect if effect in T.VALID_EFFECTS else "kenburns",
        "importance": seg.get("importance", 0.5),
        "visual_priority": seg.get("visual_priority", 0.5),
        "reason": seg.get("reason", seg.get("topic", "")),
        "source": source,  # matched | carried | generic | text
        "emphasis": bool(seg.get("emphasis", False)),
    }


def _fallback_segments(words, duration):
    """Naive semantic blocks if the LLM fails entirely (~6s chunks)."""
    segs, t, chunk = [], 0.0, 6.0
    while t < duration:
        end = min(duration, t + chunk)
        block = [w for w in words if t <= w["start"] < end]
        text = " ".join(w["text"] for w in block)
        kws = [w["text"].strip(".,!?") for w in block if len(w["text"]) > 4][:4]
        segs.append({
            "start": t, "end": end, "narration": text, "topic": text[:60],
            "entities": kws, "visual_concept": text[:50],
            "visual_type": "photo", "search_queries": kws or ["documentary"],
            "importance": 0.5, "visual_priority": 0.5, "motion": "slow_zoom",
            "reason": "keyword-based fallback",
        })
        t = end
    return segs


def build_timeline(words, duration, mode, fmt, log=lambda m: None) -> dict:
    canvas = T.FORMATS.get(fmt, T.FORMATS["youtube"])
    style = mode
    log("Konular belirleniyor...")
    used_llm = True
    try:
        segments = llm.analyze(words, duration, mode, sfx_names())
    except Exception as e:
        used_llm = False
        log(f"AI analizi yedeğe geçti ({str(e)[:60]})")
        segments = _fallback_segments(words, duration)

    segments = T.normalize_segments(segments, duration)

    log("Görseller aranıyor ve doğrulanıyor...")
    diag = {"searches": 0, "failed_searches": 0, "empty_searches": 0,
            "matched": 0, "carried": 0, "generic": 0, "text": 0}
    cache = {}
    seen = set()
    visuals = []
    sfx = []
    prev_asset = None

    for seg in segments:
        seg_dur = seg["end"] - seg["start"]
        n = max(1, min(SUBSHOT_MAX, round(seg_dur / SUBSHOT_TARGET)))
        kinds = _kinds_for(seg.get("visual_type", "photo"), style)
        queries = [q for q in (seg.get("search_queries") or []) if q]

        assets = []
        if kinds and queries:
            assets = _resolve_multi(queries, kinds, cache, diag, want=n, seen_urls=seen)
        # broaden with entities/topic if nothing specific found
        if not assets and kinds:
            broad = (seg.get("entities") or [])[:2] + [seg.get("topic", "")] + GENERIC_QUERIES
            assets = _resolve_multi(broad, kinds, cache, diag, want=1, seen_urls=seen)
            for a in assets:
                a["_generic"] = True

        sub_dur = seg_dur / n
        for i in range(n):
            s = seg["start"] + i * sub_dur
            e = seg["start"] + (i + 1) * sub_dur if i < n - 1 else seg["end"]
            motion = seg.get("motion", "slow_zoom")
            if assets:
                a = assets[i % len(assets)]
                effect = _effect_for(motion, i, style, seg.get("emphasis"))
                src = "generic" if a.get("_generic") else "matched"
                diag["generic" if a.get("_generic") else "matched"] += 1
                visuals.append(_clip(s, e, seg, a, effect, src))
                prev_asset = a
            elif prev_asset:
                # carry forward previous relevant asset with a different framing
                effect = _effect_for("pan" if i % 2 == 0 else "slow_zoom", i + 1, style)
                diag["carried"] += 1
                visuals.append(_clip(s, e, seg, prev_asset, effect, "carried"))
            else:
                # last resort: animated typography (NOT a plain solid color)
                diag["text"] += 1
                visuals.append(_clip(s, e, seg, None, "kenburns", "text"))

        if style != "documentary" and seg.get("needs_sfx") and seg.get("sfx") in sfx_names():
            sfx.append({"id": str(uuid.uuid4()), "time": round(seg["start"], 3),
                        "name": seg.get("sfx"), "volume": 0.9})

    log("Altyazılar oluşturuluyor...")
    captions = T.build_caption_lines(words)

    # diagnostics
    covered = sum((c["end"] - c["start"]) for c in visuals if c["source"] in ("matched", "carried", "generic"))
    unique_urls = {c["url"] for c in visuals if c["url"]}
    pexels = sum(1 for c in visuals if c.get("provider") == "pexels")
    giphy = sum(1 for c in visuals if c.get("provider") == "giphy")
    durs = [c["end"] - c["start"] for c in visuals]
    diagnostics = {
        "total_spoken_duration": round(duration, 2),
        "visual_coverage_pct": round(100.0 * covered / duration, 1) if duration else 0,
        "num_visual_assets": len(visuals),
        "num_unique_assets": len(unique_urls),
        "pexels_assets": pexels,
        "giphy_assets": giphy,
        "matched": diag["matched"],
        "generic_fallback": diag["generic"],
        "carried_forward": diag["carried"],
        "text_fallback": diag["text"],
        "failed_searches": diag["failed_searches"],
        "empty_searches": diag["empty_searches"],
        "total_searches": diag["searches"],
        "empty_visual_gaps": diag["text"],
        "avg_visual_duration": round(sum(durs) / len(durs), 2) if durs else 0,
    }

    return {
        "duration": round(duration, 3),
        "canvas": {"w": canvas["w"], "h": canvas["h"], "format": fmt, "label": canvas["label"]},
        "visuals": visuals,
        "captions": captions,
        "sfx": sfx,
        "music": [],
        "used_llm": used_llm,
        "style": style,
        "diagnostics": diagnostics,
    }
