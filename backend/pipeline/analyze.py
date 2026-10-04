"""Orchestrates transcript -> structured LLM shot-plan -> validated asset resolution -> timeline."""
import uuid
import requests

from providers import llm, media
from pipeline import timeline as T
from pipeline.sfx import sfx_names


SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "ShitpostStudio/1.0 (+render-validator)"
})

SUBSHOT_TARGET = 5.0
SUBSHOT_MAX = 4

GENERIC_QUERIES = [
    "documentary footage",
    "cinematic footage",
    "archival footage",
    "moody atmosphere",
    "abstract light",
    "city timelapse",
]


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
        content_type = r.headers.get("Content-Type", "")
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


def _asset_identity(candidate):
    provider = str(
        candidate.get("provider", "") or ""
    ).strip().lower()

    provider_id = str(
        candidate.get("provider_asset_id", "") or ""
    ).strip()

    url = str(
        candidate.get("url", "") or ""
    ).strip()

    if provider_id:
        return (provider, provider_id)

    return (provider, url)


def _resolve_multi(
    queries,
    kinds,
    cache,
    diag,
    want,
    seen_urls,
    seen_asset_keys,
):
    found = []

    for query in queries:
        if not query or not query.strip():
            continue

        for kind in kinds:
            results = _cached_search(
                kind,
                query,
                cache,
                diag,
            )

            for candidate in results[:12]:
                if not isinstance(candidate, dict):
                    continue

                url = str(
                    candidate.get("url", "") or ""
                ).strip()

                if not url:
                    continue

                asset_key = _asset_identity(candidate)

                if url in seen_urls:
                    continue

                if asset_key in seen_asset_keys:
                    continue

                if not _validate(url):
                    continue

                seen_urls.add(url)
                seen_asset_keys.add(asset_key)

                found.append({
                    **candidate,
                    "query_used": query,
                    "asset_key": "|".join(asset_key),
                })

                if len(found) >= want:
                    return found

    return found


def _effect_for(
    motion,
    index,
    style,
    emphasis=False,
):
    if style == "shitpost" and emphasis:
        return "shake"

    if motion == "pan":
        return "pan_right" if index % 2 == 0 else "pan_left"

    if motion == "slow_zoom":
        return "zoom_in" if index % 2 == 0 else "zoom_out"

    if motion == "static":
        return "kenburns"

    return "kenburns" if index % 2 == 0 else "zoom_in"


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
        "start": round(start, 3),
        "end": round(end, 3),
        "text": seg.get("narration")
        or seg.get("text", ""),
        "topic": seg.get("topic", ""),
        "entities": seg.get("entities", []),
        "visual_concept": seg.get(
            "visual_concept",
            "",
        ),
        "visual_type": (
            asset["type"]
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
            asset["url"]
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
            seg.get("emphasis", False)
        ),
    }


def _fallback_segments(words, duration):
    """Naive semantic blocks if the LLM fails."""
    segments = []
    current = 0.0
    chunk = 6.0

    while current < duration:
        end = min(
            duration,
            current + chunk,
        )

        block = [
            word
            for word in words
            if current <= word["start"] < end
        ]

        text = " ".join(
            word["text"]
            for word in block
        )

        keywords = [
            word["text"].strip(
                ".,!?"
            )
            for word in block
            if len(word["text"]) > 4
        ][:4]

        segments.append({
            "start": current,
            "end": end,
            "narration": text,
            "topic": text[:60],
            "entities": keywords,
            "visual_concept": text[:50],
            "visual_type": "photo",
            "search_queries": (
                keywords
                or ["documentary"]
            ),
            "importance": 0.5,
            "visual_priority": 0.5,
            "motion": "slow_zoom",
            "reason": "keyword-based fallback",
        })

        current = end

    return segments


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

    log("Konular belirleniyor...")

    used_llm = True

    try:
        segments = llm.analyze(
            words,
            duration,
            mode,
            sfx_names(),
        )
    except Exception as exc:
        used_llm = False

        log(
            "AI analizi yedeğe geçti "
            f"({str(exc)[:60]})"
        )

        segments = _fallback_segments(
            words,
            duration,
        )

    segments = T.normalize_segments(
        segments,
        duration,
    )

    log(
        "Görseller aranıyor ve "
        "doğrulanıyor..."
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
    seen_urls = set()
    seen_asset_keys = set()
    recent_asset_urls = []
    visuals = []
    sfx = []

    for seg in segments:
        segment_duration = (
            seg["end"] - seg["start"]
        )

        number_of_shots = max(
            1,
            min(
                SUBSHOT_MAX,
                round(
                    segment_duration
                    / SUBSHOT_TARGET
                ),
            ),
        )

        kinds = _kinds_for(
            seg.get(
                "visual_type",
                "photo",
            ),
            style,
        )

        queries = [
            query
            for query in (
                seg.get(
                    "search_queries",
                    [],
                )
                or []
            )
            if query
        ]

        assets = []

        if kinds and queries:
            assets = _resolve_multi(
                queries,
                kinds,
                cache,
                diagnostics_search,
                want=max(
                    number_of_shots,
                    4,
                ),
                seen_urls=seen_urls,
                seen_asset_keys=seen_asset_keys,
            )

        if not assets and kinds:
            broad_queries = (
                (seg.get("entities") or [])[:2]
                + [seg.get("topic", "")]
                + GENERIC_QUERIES
            )

            assets = _resolve_multi(
                broad_queries,
                kinds,
                cache,
                diagnostics_search,
                want=4,
                seen_urls=seen_urls,
                seen_asset_keys=seen_asset_keys,
            )

            for asset in assets:
                asset["_generic"] = True

        sub_duration = (
            segment_duration
            / number_of_shots
        )

        for index in range(
            number_of_shots
        ):
            start = (
                seg["start"]
                + index * sub_duration
            )

            if index < number_of_shots - 1:
                end = (
                    seg["start"]
                    + (index + 1)
                    * sub_duration
                )
            else:
                end = seg["end"]

            motion = seg.get(
                "motion",
                "slow_zoom",
            )

            selected_asset = None

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
