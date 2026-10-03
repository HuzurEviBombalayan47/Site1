"""Transcript -> exact sentence timing -> one unique visual per sentence."""

import re
import uuid
import requests

from providers import llm, media
from pipeline import timeline as T
from pipeline.sfx import sfx_names


SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Site1-VisualPlanner/2.0"
})


def _validate(url: str) -> bool:
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
        content_type = r.headers.get(
            "Content-Type",
            "",
        ).lower()

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
    visual_type = (
        visual_type or ""
    ).lower()

    if visual_type in (
        "stock_video",
        "video",
    ):
        return ["video", "image"]

    if (
        visual_type == "reaction"
        and style != "documentary"
    ):
        return ["gif", "image"]

    if visual_type == "graphic":
        return ["image"]

    return ["image", "video"]


def _normalize_url(url: str) -> str:
    if not url:
        return ""

    return (
        str(url)
        .strip()
        .split("?")[0]
        .rstrip("/")
    )


def _cached_search(
    kind,
    query,
    cache,
    diag,
):
    query = (
        query or ""
    ).strip()

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

        if not isinstance(
            results,
            list,
        ):
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
    Find exactly one unique usable asset.

    An asset that has already been used by an earlier
    sentence can never be selected again.
    """

    for query in queries:
        query = str(
            query or ""
        ).strip()

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
                if not isinstance(
                    candidate,
                    dict,
                ):
                    continue

                url = candidate.get(
                    "url"
                )

                normalized_url = (
                    _normalize_url(url)
                )

                if not normalized_url:
                    continue

                if normalized_url in used_urls:
                    continue

                asset_key = (
                    candidate.get(
                        "provider",
                        "",
                    ),
                    normalized_url,
                )

                if asset_key in used_asset_keys:
                    continue

                if not _validate(url):
                    continue

                used_urls.add(
                    normalized_url
                )

                used_asset_keys.add(
                    asset_key
                )

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
    if (
        style == "shitpost"
        and emphasis
    ):
        return "shake"

    motion = (
        motion
        or "slow_zoom"
    )

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
            else ""
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
            seg.get(
                "topic",
                "",
            ),
        ),

        "source": source,

        "emphasis": bool(
            seg.get(
                "emphasis",
                False,
            )
        ),
    }


def _sentence_segments(
    words,
    duration,
):
    """
    Create sentence boundaries ONLY from
    real transcript word timestamps.

    Gemini is never used to decide timing.
    """

    valid = [
        word
        for word in words
        if (
            isinstance(
                word,
                dict,
            )
            and str(
                word.get(
                    "text",
                    "",
                )
            ).strip()
        )
    ]

    if not valid:
        return []

    sentence_end = re.compile(
        r"[.!?…]+(?:[\"'”’»)]*)$"
    )

    sentences = []
    current = []

    for word in valid:
        current.append(word)

        text = str(
            word.get(
                "text",
                "",
            )
        ).strip()

        if sentence_end.search(text):
            sentences.append(
                current
            )
            current = []

    if current:
        sentences.append(
            current
        )

    result = []

    for sentence_words in sentences:
        start = float(
            sentence_words[0].get(
                "start",
                0.0,
            )
        )

        end = float(
            sentence_words[-1].get(
                "end",
                start,
            )
        )

        if end <= start:
            continue

        narration = " ".join(
            str(
                word.get(
                    "text",
                    "",
                )
            ).strip()
            for word in sentence_words
            if word.get("text")
        ).strip()

        if not narration:
            continue

        result.append({
            "start": max(
                0.0,
                start,
            ),

            "end": min(
                float(duration),
                end,
            ),

            "narration": narration,
        })

    return result


def _keywords(text):
    words_found = re.findall(
        r"[A-Za-zÇĞİÖŞÜçğıöşü0-9]{4,}",
        text or "",
    )

    seen = set()
    result = []

    for word in words_found:
        key = word.lower()

        if key in seen:
            continue

        seen.add(key)
        result.append(word)

        if len(result) >= 5:
            break

    return result


def _analyze_sentence(
    sentence,
    index,
    total,
    style,
):
    """
    Gemini determines ONLY what the visual should show.

    Gemini timing is completely ignored.
    """

    text = sentence[
        "narration"
    ]

    start = sentence[
        "start"
    ]

    end = sentence[
        "end"
    ]

    try:
        result = llm._analyze_window(
            narration=text,
            start=start,
            end=end,
        )

        if isinstance(
            result,
            list,
        ):
            result = next(
                (
                    item
                    for item in result
                    if isinstance(
                        item,
                        dict,
                    )
                ),
                None,
            )

        if isinstance(
            result,
            dict,
        ):
            seg = dict(result)
        else:
            seg = {}

    except Exception:
        seg = {}

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
        str(query).strip()
        for query in queries
        if str(query).strip()
    ]

    concept = str(
        seg.get(
            "visual_concept",
            "",
        )
        or ""
    ).strip()

    topic = str(
        seg.get(
            "topic",
            "",
        )
        or ""
    ).strip()

    if (
        concept
        and concept not in queries
    ):
        queries.insert(
            0,
            concept,
        )

    if not queries:
        queries = [
            text
        ]

    return {
        **seg,

        "start": start,

        "end": end,

        "narration": text,

        "topic": (
            topic
            or text[:120]
        ),

        "entities": (
            seg.get(
                "entities",
                [],
            )
            or _keywords(text)
        ),

        "visual_concept": (
            concept
            or text[:160]
        ),

        "visual_type": seg.get(
            "visual_type",
            "photo",
        ),

        "search_queries": queries[
            :5
        ],

        "importance": seg.get(
            "importance",
            0.5,
        ),

        "visual_priority": seg.get(
            "visual_priority",
            0.5,
        ),

        "motion": seg.get(
            "motion",
            "slow_zoom",
        ),

        "reason": seg.get(
            "reason",
            "exact transcript sentence",
        ),
    }


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
        "Gerçek transcript cümleleri çıkarılıyor..."
    )

    sentences = _sentence_segments(
        words,
        duration,
    )

    if not sentences:
        raise ValueError(
            "Transcript'te zaman damgalı cümle bulunamadı."
        )

    log(
        f"{len(sentences)} gerçek cümle bulundu."
    )

    segments = []
    used_llm = True

    for index, sentence in enumerate(
        sentences
    ):
        log(
            f"Cümle {index + 1}/{len(sentences)} analiz ediliyor..."
        )

        try:
            segments.append(
                _analyze_sentence(
                    sentence,
                    index,
                    len(sentences),
                    style,
                )
            )

        except Exception:
            used_llm = False

            segments.append({
                **sentence,

                "topic": sentence[
                    "narration"
                ][:120],

                "entities": _keywords(
                    sentence[
                        "narration"
                    ]
                ),

                "visual_concept": (
                    sentence[
                        "narration"
                    ][:160]
                ),

                "visual_type": "photo",

                "search_queries": [
                    sentence[
                        "narration"
                    ]
                ],

                "importance": 0.5,

                "visual_priority": 0.5,

                "motion": "slow_zoom",

                "reason": (
                    "sentence fallback"
                ),
            })

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

        asset = _resolve_one(
            queries,
            kinds,
            cache,
            diagnostics_search,
            used_urls,
            used_asset_keys,
        )

        if asset is None:
            fallback_queries = []

            for value in [
                seg.get(
                    "visual_concept",
                    "",
                ),
                seg.get(
                    "topic",
                    "",
                ),
                seg.get(
                    "narration",
                    "",
                ),
            ]:
                value = str(
                    value or ""
                ).strip()

                if (
                    value
                    and value
                    not in fallback_queries
                ):
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
            diagnostics_search[
                "matched"
            ] += 1

            visuals.append(
                _clip(
                    start,
                    end,
                    seg,
                    asset,
                    _effect_for(
                        seg.get(
                            "motion"
                        ),
                        index,
                        style,
                        seg.get(
                            "emphasis",
                            False,
                        ),
                    ),
                    "matched",
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

        if (
            style != "documentary"
            and seg.get(
                "needs_sfx"
            )
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

    # Keep transcript timing exactly as produced above.
    visuals = [
        clip
        for clip in visuals
        if (
            clip["end"]
            > clip["start"]
            and clip["start"] >= 0
            and clip["end"]
            <= float(duration)
            + 0.001
        )
    ]

    visuals.sort(
        key=lambda clip: (
            clip["start"],
            clip["end"],
        )
    )

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
        == "matched"
    )

    unique_urls = {
        _normalize_url(
            clip["url"]
        )
        for clip in visuals
        if clip.get("url")
    }

    durations = [
        clip["end"] - clip["start"]
        for clip in visuals
    ]

    diagnostics = {
        "total_spoken_duration": round(
            float(duration),
            2,
        ),

        "visual_coverage_pct": (
            round(
                100.0
                * covered
                / float(duration),
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

        "pexels_assets": sum(
            1
            for clip in visuals
            if clip.get("provider")
            == "pexels"
        ),

        "giphy_assets": sum(
            1
            for clip in visuals
            if clip.get("provider")
            == "giphy"
        ),

        "matched": diagnostics_search[
            "matched"
        ],

        "generic_fallback": 0,

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
            float(duration),
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
