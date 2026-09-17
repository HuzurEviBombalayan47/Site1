"""Timeline builder: turns LLM segments + fetched assets into a full timeline.

Also builds caption lines from word-level timings.
"""
import uuid

FORMATS = {
    "youtube": {"w": 1920, "h": 1080, "label": "YouTube 16:9"},
    "shorts": {"w": 1080, "h": 1920, "label": "Shorts 9:16"},
    "square": {"w": 1080, "h": 1080, "label": "Square 1:1"},
}

VALID_EFFECTS = {"kenburns", "zoom_in", "zoom_out", "pan_left", "pan_right", "shake"}


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def normalize_segments(segments: list, duration: float) -> list:
    """Sort, clamp and make segments contiguous covering 0..duration."""
    segs = []
    for s in segments:
        try:
            start = float(s.get("start", 0))
            end = float(s.get("end", 0))
        except (TypeError, ValueError):
            continue
        if end <= start:
            continue
        segs.append({**s, "start": start, "end": end})
    segs.sort(key=lambda x: x["start"])
    if not segs:
        return []
    # make contiguous
    segs[0]["start"] = 0.0
    for i in range(len(segs) - 1):
        mid = (segs[i]["end"] + segs[i + 1]["start"]) / 2.0
        segs[i]["end"] = mid
        segs[i + 1]["start"] = mid
    segs[-1]["end"] = duration
    # clamp
    for s in segs:
        s["start"] = _clamp(s["start"], 0.0, duration)
        s["end"] = _clamp(s["end"], s["start"] + 0.3, duration)
    return segs


def build_caption_lines(words: list, max_words: int = 6, max_dur: float = 2.6) -> list:
    """Group words into readable caption lines with timing."""
    lines = []
    cur = []
    for w in words:
        if not cur:
            cur = [w]
            continue
        line_start = cur[0]["start"]
        if len(cur) >= max_words or (w["end"] - line_start) > max_dur:
            lines.append(cur)
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(cur)

    out = []
    for group in lines:
        out.append(
            {
                "id": str(uuid.uuid4()),
                "start": round(group[0]["start"], 3),
                "end": round(group[-1]["end"], 3),
                "text": " ".join(g["text"] for g in group),
                "words": [
                    {"text": g["text"], "start": round(g["start"], 3), "end": round(g["end"], 3)}
                    for g in group
                ],
            }
        )
    return out


def default_caption_style():
    return {
        "enabled": True,
        "font": "DejaVu Sans",
        "size": 54,
        "color": "#FFFFFF",
        "outline_color": "#000000",
        "outline_width": 4,
        "highlight_color": "#FFE600",
        "position": "bottom",  # bottom | center | top
        "bold": True,
        "uppercase": False,
    }


def make_clip(seg, asset, effect):
    return {
        "id": str(uuid.uuid4()),
        "start": round(seg["start"], 3),
        "end": round(seg["end"], 3),
        "text": seg.get("text", ""),
        "topic": seg.get("topic", ""),
        "entities": seg.get("entities", []),
        "visual_type": asset["type"] if asset else "text",
        "search_query": seg.get("search_query", ""),
        "url": asset["url"] if asset else None,
        "preview": asset.get("preview") if asset else None,
        "provider": asset.get("provider") if asset else None,
        "credit": asset.get("credit") if asset else None,
        "effect": effect if effect in VALID_EFFECTS else "kenburns",
        "emphasis": bool(seg.get("emphasis", False)),
        "reason": seg.get("topic", ""),
    }


def make_sfx(seg):
    return {
        "id": str(uuid.uuid4()),
        "time": round(seg["start"], 3),
        "name": seg.get("sfx"),
        "volume": 0.9,
    }
