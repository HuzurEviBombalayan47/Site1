import uuid
import requests

from providers import llm, media
from pipeline import timeline as T
from pipeline.sfx import sfx_names


SUBSHOT_TARGET = 5.0
SUBSHOT_MAX = 4


GENERIC_QUERIES = [
    "documentary footage",
    "archival footage",
    "news footage",
    "real world footage",
    "historical photograph",
    "stock footage",
]


def _validate(url):
    if not url:
        return False

    try:
        r = requests.head(
            url,
            timeout=8,
            allow_redirects=True,
        )

        if r.status_code >= 400:
            return False

        content_type = (
            r.headers.get("content-type", "")
            .lower()
        )

        return (
            "image" in content_type
            or "video" in content_type
            or "octet-stream" in content_type
            or not content_type
        )

    except Exception:
        return False


def _kinds_for(asset_type, mode):
    if asset_type == "stock_video":
        return ["video", "image"]

    if asset_type == "reaction" and mode != "documentary":
        return ["gif", "image"]

    if asset_type == "graphic":
        return []

    return ["image", "video"]


def _cached_search(
    query,
    kinds,
    limit,
    cache,
):
    key = (
        query.lower().strip(),
        tuple(kinds),
        limit,
    )

    if key in cache:
        return cache[key]

    try:
        result = media.search(
            query=query,
            kinds=kinds,
            limit=limit,
        )

        if not isinstance(result, list):
            result = []

    except Exception as exc:
        print(
            f"[MEDIA] search failed for {query!r}: "
            f"{str(exc)[:300]}",
            flush=True,
        )
        result = []

    cache[key] = result
    return result


def _asset_identity(asset):
    return (
        asset.get("url")
        or asset.get("src")
        or asset.get("id")
        or str(asset)
    )


def _resolve_multi(
    queries,
    kinds,
    limit,
    cache,
    used,
):
    found = []

    for query in queries:
        query = str(query).strip()

        if not query:
            continue

        assets = _cached_search(
            query=query,
            kinds=kinds,
            limit=limit,
            cache=cache,
        )

        for asset in assets:

            if not isinstance(asset, dict):
                continue

            url = (
                asset.get("url")
                or asset.get("src")
                or asset.get("video_url")
                or asset.get("image_url")
            )

            if not url:
                continue

            identity = _asset_identity(asset)

            if identity in used:
                continue

            if not _validate(url):
                continue

            asset = dict(asset)
            asset["url"] = url
            asset["query"] = query

            used.add(identity)
            found.append(asset)

            if len(found) >= limit:
                return found

    return found


def _effect_for(
    index,
    visual_type="photo",
):
    effects = [
        "slow_zoom",
        "pan_left",
        "pan_right",
        "kenburns",
    ]

    if visual_type == "video":
        return "none"

    return effects[index % len(effects)]


def _clip(
    asset,
    start,
    end,
    index,
):
    visual_type = (
        asset.get("type")
        or asset.get("media_type")
        or "photo"
    )

    return {
        "id": str(uuid.uuid4()),
        "start": round(start, 3),
        "end": round(end, 3),
        "url": asset.get("url"),
        "type": visual_type,
        "effect": _effect_for(
            index,
            visual_type,
        ),
        "query": asset.get("query"),
        "provider": asset.get("provider"),
    }


def _sanitize_visual_timeline(
    clips,
    duration,
):
    if not clips:
        return []

    clips = sorted(
        clips,
        key=lambda x: float(x.get("start", 0)),
    )

    result = []
    cursor = 0.0

    for clip in clips:

        start = max(
            cursor,
            float(clip.get("start", 0)),
        )

        end = min(
            duration,
            float(clip.get("end", duration)),
        )

        if end <= start:
            continue

        clip = dict(clip)
        clip["start"] = round(start, 3)
        clip["end"] = round(end, 3)

        result.append(clip)

        cursor = end

        if cursor >= duration:
            break

    return result


def _fallback_segments(
    words,
    duration,
):
    segments = []

    if not words:
        return segments

    chunk_start = 0.0
    chunk_words = []

    for word in words:

        try:
            start = float(word.get("start", 0))
        except Exception:
            start = 0.0

        if (
            start - chunk_start >= 6.0
            and chunk_words
        ):
            text = " ".join(
                str(w.get("text", "")).strip()
                for w in chunk_words
                if str(w.get("text", "")).strip()
            )

            keywords = [
                x
                for x in text.split()
                if len(x) >= 4
            ]

            query = " ".join(
                keywords[:6]
            ) or GENERIC_QUERIES[
                len(segments) % len(GENERIC_QUERIES)
            ]

            segments.append(
                {
                    "start": chunk_start,
                    "end": min(
                        duration,
                        start,
                    ),
                    "narration": text,
                    "visual_concept": query,
                    "search_queries": [
                        query
                    ],
                    "visual_type": "photo",
                    "motion": "slow_zoom",
                }
            )

            chunk_words = []
            chunk_start = start

        chunk_words.append(word)

    if chunk_words:

        text = " ".join(
            str(w.get("text", "")).strip()
            for w in chunk_words
            if str(w.get("text", "")).strip()
        )

        keywords = [
            x
            for x in text.split()
            if len(x) >= 4
        ]

        query = " ".join(
            keywords[:6]
        ) or GENERIC_QUERIES[
            len(segments) % len(GENERIC_QUERIES)
        ]

        segments.append(
            {
                "start": chunk_start,
                "end": duration,
                "narration": text,
                "visual_concept": query,
                "search_queries": [
                    query
                ],
                "visual_type": "photo",
                "motion": "slow_zoom",
            }
        )

    return segments


def build_timeline(
    words,
    duration,
    mode="documentary",
    fmt="16:9",
    log=None,
):
    """
    Build the visual timeline.

    Gemini is responsible for determining
    subject-specific visual queries.
    """

    if log is None:
        log = []

    cache = {}
    used_assets = set()
    clips = []

    try:
        segments = llm.analyze(
            words,
            duration,
            mode,
            sfx_names(),
        )

        used_llm = bool(segments)

        log.append(
            {
                "event": "llm_analysis",
                "segments": len(segments),
                "used_llm": used_llm,
            }
        )

    except Exception as exc:

        print(
            f"[ANALYZE] LLM failed, using fallback: "
            f"{str(exc)[:500]}",
            flush=True,
        )

        log.append(
            {
                "event": "llm_fallback",
                "error": str(exc)[:500],
            }
        )

        segments = _fallback_segments(
            words,
            duration,
        )

    if not segments:
        segments = _fallback_segments(
            words,
            duration,
        )

    for segment_index, segment in enumerate(
        segments
    ):

        try:
            seg_start = float(
                segment.get(
                    "start",
                    0,
                )
            )

            seg_end = float(
                segment.get(
                    "end",
                    duration,
                )
            )

        except Exception:
            continue

        seg_start = max(
            0.0,
            min(seg_start, duration),
        )

        seg_end = max(
            seg_start,
            min(seg_end, duration),
        )

        if seg_end <= seg_start:
            continue

        segment_duration = (
            seg_end - seg_start
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

        queries = (
            segment.get(
                "search_queries"
            )
            or []
        )

        queries = [
            str(q).strip()
            for q in queries
            if str(q).strip()
        ]

        if not queries:

            concept = (
                segment.get(
                    "visual_concept"
                )
                or segment.get(
                    "topic"
                )
                or segment.get(
                    "narration"
                )
                or "documentary subject"
            )

            queries = [
                str(concept).strip()
            ]

        asset_type = (
            segment.get(
                "visual_type"
            )
            or "photo"
        )

        kinds = _kinds_for(
            asset_type,
            mode,
        )

        assets = _resolve_multi(
            queries=queries,
            kinds=kinds,
            limit=number_of_shots,
            cache=cache,
            used=used_assets,
        )

        # If the first provider search does not
        # return enough unique assets, broaden
        # the search using the actual topic.
        if len(assets) < number_of_shots:

            concept = (
                segment.get(
                    "visual_concept"
                )
                or segment.get(
                    "topic"
                )
                or segment.get(
                    "narration"
                )
                or "documentary subject"
            )

            broad_queries = [
                str(concept).strip(),
                *GENERIC_QUERIES,
            ]

            extra = _resolve_multi(
                queries=broad_queries,
                kinds=kinds,
                limit=number_of_shots
                - len(assets),
                cache=cache,
                used=used_assets,
            )

            assets.extend(extra)

        if not assets:
            log.append(
                {
                    "event": "no_visual_assets",
                    "segment": segment_index,
                    "queries": queries,
                }
            )
            continue

        shot_duration = (
            segment_duration
            / len(assets)
        )

        for shot_index, asset in enumerate(
            assets
        ):

            shot_start = (
                seg_start
                + shot_index
                * shot_duration
            )

            shot_end = (
                seg_start
                + (shot_index + 1)
                * shot_duration
            )

            clips.append(
                _clip(
                    asset=asset,
                    start=shot_start,
                    end=shot_end,
                    index=(
                        segment_index
                        + shot_index
                    ),
                )
            )

        log.append(
            {
                "event": "visual_segment",
                "segment": segment_index,
                "start": seg_start,
                "end": seg_end,
                "queries": queries,
                "assets": len(assets),
            }
        )

    clips = _sanitize_visual_timeline(
        clips,
        duration,
    )

    captions = []

    for word in words or []:

        try:
            start = float(
                word.get("start", 0)
            )
            end = float(
                word.get("end", start)
            )
        except Exception:
            continue

        text = str(
            word.get("text", "")
        ).strip()

        if not text:
            continue

        captions.append(
            {
                "start": start,
                "end": end,
                "text": text,
            }
        )

    diagnostics = {
        "used_llm": any(
            x.get("event")
            == "llm_analysis"
            and x.get("used_llm")
            for x in log
            if isinstance(x, dict)
        ),
        "num_clips": len(clips),
        "num_unique_assets": len(
            used_assets
        ),
        "total_searches": len(cache),
        "duration": duration,
    }

    return {
        "clips": clips,
        "captions": captions,
        "diagnostics": diagnostics,
        "log": log,
    }
