"""Transcript -> sentence-based visual plan -> validated assets -> timeline.

Each narration sentence/segment receives exactly one visual asset.
Visuals never overlap and the same asset URL is never reused.
"""

import re
import uuid
import requests

from providers import llm, media
from pipeline import timeline as T
from pipeline.sfx import sfx_names

SESSION = requests.Session()
SESSION.headers.update({
"User-Agent": "Site1-VisualPlanner/1.0"
})

Fallback only. These are intentionally not used as normal search queries.

GENERIC_QUERIES = [
"documentary subject",
]

def _validate(url: str) -> bool:
"""Check that a media URL is actually reachable."""
if not url:
return False

try:
    r = SESSION.get(
        url,
        stream=True,
        timeout=12,
        headers={"Range": "bytes=0-4096"},
    )

    ok = r.status_code in (200, 206)
    content_type = r.headers.get("Content-Type", "").lower()
    r.close()

    return ok and (
        content_type.startswith("image")
        or content_type.startswith("video")
        or "octet-stream" in content_type
        or content_type == ""
    )

except Exception:
    return False

def _kinds_for(visual_type: str, style: str):
"""Determine which media providers/types can satisfy a visual."""
visual_type = (visual_type or "").lower()

if visual_type in ("stock_video", "video"):
    return ["video", "image"]

if visual_type == "reaction" and style != "documentary":
    return ["gif", "image"]

if visual_type == "graphic":
    return ["image"]

return ["image", "video"]

def _normalize_url(url: str) -> str:
"""Normalize URLs enough to catch trivial duplicates."""
if not url:
return ""

return (
    str(url)
    .strip()
    .split("?")[0]
    .rstrip("/")
)

def _cached_search(kind, query, cache, diag):
"""Search media providers with a per-job cache."""
query = (query or "").strip()

if not query:
    return []

key = (
    kind,
    query.lower(),
)

if key in cache:
    return cache[key]

try:
    diag["searches"] += 1

    results = media.search(
        kind,
        query,
    )

    if not isinstance(results, list):
        results = []

except Exception:
    diag["failed_searches"] += 1
    results = []

if not results:
    diag["empty_searches"] += 1

cache[key] = results

return results

def _resolve_one(
queries,
kinds,
cache,
diag,
used_urls,
used_asset_keys,
):
"""
Find exactly ONE new asset for the current sentence.

Important:
- Never returns an already-used URL.
- Searches query by query.
- Validates every candidate.
- Stops as soon as one unique usable asset is found.
"""

for query in queries:
    query = (query or "").strip()

    if not query:
        continue

    for kind in kinds:
        results = _cached_search(
            kind,
            query,
            cache,
            diag,
        )

        for candidate in results:
            if not isinstance(candidate, dict):
                continue

            url = candidate.get("url")

            if not url:
                continue

            normalized_url = _normalize_url(url)

            if not normalized_url:
                continue

            # Hard duplicate protection.
            if normalized_url in used_urls:
                continue

            # Additional protection for provider + URL.
            asset_key = (
                candidate.get("provider", ""),
                normalized_url,
            )

            if asset_key in used_asset_keys:
                continue

            # Do not accept dead/broken media.
            if not _validate(url):
                continue

            used_urls.add(normalized_url)
            used_asset_keys.add(asset_key)

            return {
                **candidate,
                "query_used": query,
            }

return None

def _effect_for(
motion,
index,
style,
emphasis=False,
):
"""Select a subtle motion effect for a single sentence visual."""

if style == "shitpost" and emphasis:
    return "shake"

motion = motion or "slow_zoom"

if motion == "pan":
    return (
        "pan_right"
        if index % 2 == 0
        else "pan_left"
    )

if motion == "slow_zoom":
    return (
        "zoom_in"
        if index % 2 == 0
        else "zoom_out"
    )

if motion == "static":
    return "kenburns"

return (
    "kenburns"
    if index % 2 == 0
    else "zoom_in"
)

def _clip(
start,
end,
seg,
asset,
effect,
source,
):
"""Create one timeline visual clip."""

return {
    "id": str(uuid.uuid4()),

    "start": round(
        max(0.0, start),
        3,
    ),

    "end": round(
        max(start, end),
        3,
    ),

    "text": (
        seg.get("narration")
        or seg.get("text")
        or ""
    ),

    "topic": seg.get(
        "topic",
        "",
    ),

    "entities": seg.get(
        "entities",
        [],
    ),

    "visual_concept": seg.get(
        "visual_concept",
        "",
    ),

    "visual_type": (
        asset.get("type")
        if asset
        else "text"
    ),

    "planned_type": seg.get(
        "visual_type",
        "photo",
    ),

    "search_query": (
        asset.get("query_used")
        if asset
        else (
            seg.get("search_queries")
            or [""]
        )[0]
    ),

    "search_queries": seg.get(
        "search_queries",
        [],
    ),

    "url": (
        asset.get("url")
        if asset
        else None
    ),

    "preview": (
        asset.get("preview")
        if asset
        else None
    ),

    "provider": (
        asset.get("provider")
        if asset
        else None
    ),

    "credit": (
        asset.get("credit")
        if asset
        else None
    ),

    "effect": (
        effect
        if effect in T.VALID_EFFECTS
        else "kenburns"
    ),

    "importance": seg.get(
        "importance",
        0.5,
    ),

    "visual_priority": seg.get(
        "visual_priority",
        0.5,
    ),

    "reason": seg.get(
        "reason",
        seg.get("topic", ""),
    ),

    "source": source,

    "emphasis": bool(
        seg.get(
            "emphasis",
            False,
        )
    ),
}

def _sentence_fallback(words, duration):
"""
Build sentence-like segments directly from transcript word timings.

This is only used if Gemini fails.

We split on punctuation first, then use word timestamps so
every resulting sentence gets its own exact time range.
"""

if not words:
    return []

segments = []
current_words = []

sentence_end_re = re.compile(
    r"[.!?…]+$"
)

for word in words:
    if not isinstance(word, dict):
        continue

    text = str(
        word.get("text", "")
    ).strip()

    if not text:
        continue

    current_words.append(word)

    if sentence_end_re.search(text):
        start = float(
            current_words[0].get(
                "start",
                0,
            )
        )

        end = float(
            current_words[-1].get(
                "end",
                start,
            )
        )

        narration = " ".join(
            str(w.get("text", "")).strip()
            for w in current_words
            if w.get("text")
        ).strip()

        keywords = [
            str(w.get("text", "")).strip(
                ".,!?;:"
            )
            for w in current_words
            if len(
                str(
                    w.get(
                        "text",
                        "",
                    )
                ).strip()
            ) > 4
        ][:5]

        segments.append({
            "start": start,
            "end": end,
            "narration": narration,
            "topic": narration[:100],
            "entities": keywords,
            "visual_concept": narration[:100],
            "visual_type": "photo",
            "search_queries": (
                [narration]
                + keywords[:2]
            ),
            "importance": 0.5,
            "visual_priority": 0.5,
            "motion": "slow_zoom",
            "reason": "transcript sentence fallback",
        })

        current_words = []

# Remaining words without punctuation.
if current_words:
    start = float(
        current_words[0].get(
            "start",
            0,
        )
    )

    end = float(
        current_words[-1].get(
            "end",
            duration,
        )
    )

    narration = " ".join(
        str(w.get("text", "")).strip()
        for w in current_words
        if w.get("text")
    ).strip()

    keywords = [
        str(w.get("text", "")).strip(
            ".,!?;:"
        )
        for w in current_words
        if len(
            str(
                w.get(
                    "text",
                    "",
                )
            ).strip()
        ) > 4
    ][:5]

    segments.append({
        "start": start,
        "end": end,
        "narration": narration,
        "topic": narration[:100],
        "entities": keywords,
        "visual_concept": narration[:100],
        "visual_type": "photo",
        "search_queries": (
            [narration]
            + keywords[:2]
        ),
        "importance": 0.5,
        "visual_priority": 0.5,
        "motion": "slow_zoom",
        "reason": "transcript remainder fallback",
    })

return segments

def _make_segments_from_llm(words, duration):
"""
Ask Gemini for sentence-level visual instructions.

Gemini decides the visual/search query, but transcript timestamps
remain the authority for timing.
"""

narration = " ".join(
    str(word.get("text", "")).strip()
    for word in words
    if isinstance(word, dict)
    and word.get("text")
).strip()

if not narration:
    raise ValueError(
        "Transcript contains no usable text"
    )

segments = llm._analyze_window(
    narration=narration,
    start=0,
    end=float(duration),
)

if not isinstance(
    segments,
    list,
):
    raise ValueError(
        "Gemini did not return a segment list"
    )

cleaned = []

for seg in segments:
    if not isinstance(seg, dict):
        continue

    text = (
        seg.get("narration")
        or seg.get("text")
        or ""
    ).strip()

    if not text:
        continue

    queries = seg.get(
        "search_queries",
        [],
    )

    if isinstance(
        queries,
        str,
    ):
        queries = [queries]

    queries = [
        str(q).strip()
        for q in queries
        if str(q).strip()
    ]

    if not queries:
        queries = [
            str(
                seg.get(
                    "visual_concept",
                    "",
                )
            ).strip()
        ]

    seg["narration"] = text
    seg["search_queries"] = [
        q
        for q in queries
        if q
    ][:4]

    cleaned.append(seg)

if not cleaned:
    raise ValueError(
        "Gemini returned no usable visual segments"
    )

return cleaned

def _align_segments_to_transcript(
segments,
words,
duration,
):
"""
Convert Gemini's semantic segments into non-overlapping timeline
segments.

The Gemini timestamps are NOT trusted blindly.

We use the number/order of returned segments to divide the actual
transcript timing, while guaranteeing:
    0 <= start < end <= duration
    segment N ends exactly where segment N+1 starts
"""

if not segments:
    return []

# Get valid word timings.
valid_words = [
    w
    for w in words
    if isinstance(w, dict)
    and w.get("text")
]

if not valid_words:
    return T.normalize_segments(
        segments,
        duration,
    )

total = len(segments)

# Map each Gemini segment to an approximate section of the
# actual transcript. This prevents random Gemini timestamps
# from creating overlaps.
aligned = []

for index, seg in enumerate(
    segments
):
    start_ratio = (
        index / total
    )

    end_ratio = (
        (index + 1) / total
    )

    start_index = int(
        len(valid_words)
        * start_ratio
    )

    end_index = int(
        len(valid_words)
        * end_ratio
    ) - 1

    start_index = max(
        0,
        min(
            start_index,
            len(valid_words) - 1,
        ),
    )

    end_index = max(
        start_index,
        min(
            end_index,
            len(valid_words) - 1,
        ),
    )

    start = float(
        valid_words[start_index].get(
            "start",
            0,
        )
    )

    end = float(
        valid_words[end_index].get(
            "end",
            duration,
        )
    )

    # Last segment always reaches the actual audio end.
    if index == total - 1:
        end = float(duration)

    # Make boundaries contiguous.
    if aligned:
        start = aligned[-1]["end"]

    end = max(
        end,
        start + 0.3,
    )

    end = min(
        end,
        float(duration),
    )

    if end <= start:
        continue

    aligned.append({
        **seg,
        "start": start,
        "end": end,
    })

return T.normalize_segments(
    aligned,
    duration,
)

def build_timeline(
words,
duration,
mode,
fmt,
log=lambda message: None,
) -> dict:

canvas = T.FORMATS.get(
    fmt,
    T.FORMATS["youtube"],
)

style = mode

log(
    "Cümleler analiz ediliyor..."
)

used_llm = True

try:
    semantic_segments = (
        _make_segments_from_llm(
            words,
            duration,
        )
    )

    segments = (
        _align_segments_to_transcript(
            semantic_segments,
            words,
            duration,
        )
    )

    if not segments:
        raise ValueError(
            "No aligned segments"
        )

except Exception as exc:
    used_llm = False

    log(
        "AI analizi yedeğe geçti "
        f"({str(exc)[:120]})"
    )

    segments = _sentence_fallback(
        words,
        duration,
    )

    segments = T.normalize_segments(
        segments,
        duration,
    )

log(
    f"{len(segments)} cümle/bölüm için "
    "ayrı görseller aranıyor..."
)

diagnostics_search = {
    "searches": 0,
    "failed_searches": 0,
    "empty_searches": 0,
    "matched": 0,
    "carried": 0,
    "generic": 0,
    "text": 0,
}

cache = {}

# Global duplicate protection.
used_urls = set()
used_asset_keys = set()

visuals = []
sfx = []

for index, seg in enumerate(
    segments
):
    start = float(
        seg["start"]
    )

    end = float(
        seg["end"]
    )

    if end <= start:
        continue

    kinds = _kinds_for(
        seg.get(
            "visual_type",
            "photo",
        ),
        style,
    )

    queries = [
        str(query).strip()
        for query in (
            seg.get(
                "search_queries",
                [],
            )
            or []
        )
        if str(query).strip()
    ]

    # Strongest queries first.
    primary_queries = queries[:4]

    asset = None

    if kinds and primary_queries:
        asset = _resolve_one(
            primary_queries,
            kinds,
            cache,
            diagnostics_search,
            used_urls,
            used_asset_keys,
        )

    # If the first search did not work, try concrete transcript
    # information. Still no generic cinematic filler.
    if asset is None and kinds:
        fallback_queries = []

        for value in [
            seg.get(
                "visual_concept",
                "",
            ),
            seg.get(
                "narration",
                "",
            ),
            seg.get(
                "topic",
                "",
            ),
        ]:
            value = str(
                value or ""
            ).strip()

            if value and value not in fallback_queries:
                fallback_queries.append(
                    value
                )

        asset = _resolve_one(
            fallback_queries,
            kinds,
            cache,
            diagnostics_search,
            used_urls,
            used_asset_keys,
        )

    if asset:
        source = "matched"

        diagnostics_search[
            "matched"
        ] += 1

        effect = _effect_for(
            seg.get(
                "motion",
                "slow_zoom",
            ),
            index,
            style,
            seg.get(
                "emphasis",
                False,
            ),
        )

        visuals.append(
            _clip(
                start,
                end,
                seg,
                asset,
                effect,
                source,
            )
        )

    else:
        diagnostics_search[
            "text"
        ] += 1

        visuals.append(
            _clip(
                start,
                end,
                seg,
                None,
                "kenburns",
                "text",
            )
        )

    # SFX remain attached to the sentence start.
    if (
        style != "documentary"
        and seg.get("needs_sfx")
        and seg.get("sfx")
        in sfx_names()
    ):
        sfx.append({
            "id": str(uuid.uuid4()),
            "time": round(
                start,
                3,
            ),
            "name": seg.get(
                "sfx"
            ),
            "volume": 0.9,
        })

# Final safety pass:
# sort by start and make absolutely sure clips cannot overlap.
visuals.sort(
    key=lambda clip: (
        clip["start"],
        clip["end"],
    )
)

safe_visuals = []

cursor = 0.0

for clip in visuals:
    start = max(
        float(clip["start"]),
        cursor,
    )

    end = min(
        float(clip["end"]),
        float(duration),
    )

    if end <= start:
        continue

    clip["start"] = round(
        start,
        3,
    )

    clip["end"] = round(
        end,
        3,
    )

    safe_visuals.append(
        clip
    )

    cursor = end

visuals = safe_visuals

log(
    "Altyazılar oluşturuluyor..."
)

captions = T.build_caption_lines(
    words
)

covered = sum(
    clip["end"] - clip["start"]
    for clip in visuals
    if clip["source"]
    in (
        "matched",
        "generic",
    )
)

unique_urls = {
    _normalize_url(
        clip["url"]
    )
    for clip in visuals
    if clip.get("url")
}

pexels_count = sum(
    1
    for clip in visuals
    if clip.get("provider")
    == "pexels"
)

giphy_count = sum(
    1
    for clip in visuals
    if clip.get("provider")
    == "giphy"
)

durations = [
    clip["end"] - clip["start"]
    for clip in visuals
]

diagnostics = {
    "total_spoken_duration": round(
        duration,
        2,
    ),

    "visual_coverage_pct": (
        round(
            100.0
            * covered
            / duration,
            1,
        )
        if duration
        else 0
    ),

    "num_visual_assets": len(
        visuals
    ),

    "num_unique_assets": len(
        unique_urls
    ),

    "pexels_assets": pexels_count,

    "giphy_assets": giphy_count,

    "matched": diagnostics_search[
        "matched"
    ],

    "generic_fallback": diagnostics_search[
        "generic"
    ],

    "carried_forward": 0,

    "text_fallback": diagnostics_search[
        "text"
    ],

    "failed_searches": diagnostics_search[
        "failed_searches"
    ],

    "empty_searches": diagnostics_search[
        "empty_searches"
    ],

    "total_searches": diagnostics_search[
        "searches"
    ],

    "empty_visual_gaps": diagnostics_search[
        "text"
    ],

    "avg_visual_duration": (
        round(
            sum(durations)
            / len(durations),
            2,
        )
        if durations
        else 0
    ),
}

return {
    "duration": round(
        duration,
        3,
    ),

    "canvas": {
        "w": canvas["w"],
        "h": canvas["h"],
        "format": fmt,
        "label": canvas["label"],
    },

    "visuals": visuals,

    "captions": captions,

    "sfx": sfx,

    "music": [],

    "used_llm": used_llm,

    "style": style,

    "diagnostics": diagnostics,
}          selected_asset = None

            for candidate in assets:
                candidate_url = (
                    candidate.get("url")
                )

                if not candidate_url:
                    continue

                if (
                    candidate_url
                    in recent_asset_urls
                ):
                    continue

                selected_asset = candidate
                break

            if selected_asset:
                effect = _effect_for(
                    motion,
                    index,
                    style,
                    seg.get(
                        "emphasis",
                        False,
                    ),
                )

                if selected_asset.get(
                    "_generic",
                    False,
                ):
                    source = "generic"
                    diagnostics_search[
                        "generic"
                    ] += 1
                else:
                    source = "matched"
                    diagnostics_search[
                        "matched"
                    ] += 1

                visuals.append(
                    _clip(
                        start,
                        end,
                        seg,
                        selected_asset,
                        effect,
                        source,
                    )
                )

                previous_asset = (
                    selected_asset
                )

                selected_url = (
                    selected_asset.get(
                        "url"
                    )
                )

                if selected_url:
                    recent_asset_urls.append(
                        selected_url
                    )

                    recent_asset_urls = (
                        recent_asset_urls[-3:]
                    )

            else:
                diagnostics_search[
                    "text"
                ] += 1

                visuals.append(
                    _clip(
                        start,
                        end,
                        seg,
                        None,
                        "kenburns",
                        "text",
                    )
                )

        if (
            style != "documentary"
            and seg.get("needs_sfx")
            and seg.get("sfx")
            in sfx_names()
        ):
            sfx.append({
                "id": str(uuid.uuid4()),
                "time": round(
                    seg["start"],
                    3,
                ),
                "name": seg.get("sfx"),
                "volume": 0.9,
            })

    log("Altyazılar oluşturuluyor...")

    captions = T.build_caption_lines(
        words
    )

    covered = sum(
        clip["end"] - clip["start"]
        for clip in visuals
        if clip["source"]
        in (
            "matched",
            "generic",
        )
    )

    unique_urls = {
        clip["url"]
        for clip in visuals
        if clip["url"]
    }

    pexels_count = sum(
        1
        for clip in visuals
        if clip.get("provider")
        == "pexels"
    )

    giphy_count = sum(
        1
        for clip in visuals
        if clip.get("provider")
        == "giphy"
    )

    durations = [
        clip["end"] - clip["start"]
        for clip in visuals
    ]

    diagnostics = {
        "total_spoken_duration": round(
            duration,
            2,
        ),
        "visual_coverage_pct": (
            round(
                100.0
                * covered
                / duration,
                1,
            )
            if duration
            else 0
        ),
        "num_visual_assets": len(
            visuals
        ),
        "num_unique_assets": len(
            unique_urls
        ),
        "pexels_assets": pexels_count,
        "giphy_assets": giphy_count,
        "matched": diagnostics_search[
            "matched"
        ],
        "generic_fallback": diagnostics_search[
            "generic"
        ],
        "carried_forward": diagnostics_search[
            "carried"
        ],
        "text_fallback": diagnostics_search[
            "text"
        ],
        "failed_searches": diagnostics_search[
            "failed_searches"
        ],
        "empty_searches": diagnostics_search[
            "empty_searches"
        ],
        "total_searches": diagnostics_search[
            "searches"
        ],
        "empty_visual_gaps": diagnostics_search[
            "text"
        ],
        "avg_visual_duration": (
            round(
                sum(durations)
                / len(durations),
                2,
            )
            if durations
            else 0
        ),
    }

    return {
        "duration": round(
            duration,
            3,
        ),
        "canvas": {
            "w": canvas["w"],
            "h": canvas["h"],
            "format": fmt,
            "label": canvas["label"],
        },
        "visuals": visuals,
        "captions": captions,
        "sfx": sfx,
        "music": [],
        "used_llm": used_llm,
        "style": style,
        "diagnostics": diagnostics,
    }
