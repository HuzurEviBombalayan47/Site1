"""Media search providers: Pexels (images + videos) and Giphy (gifs). Modular."""
import os
import requests

PEXELS_IMG = "https://api.pexels.com/v1/search"
PEXELS_VID = "https://api.pexels.com/videos/search"
GIPHY_SEARCH = "https://api.giphy.com/v1/gifs/search"


def _pexels_key():
    k = os.environ.get("PEXELS_API_KEY")
    if not k:
        raise RuntimeError("PEXELS_API_KEY is not configured")
    return k


def _giphy_key():
    k = os.environ.get("GIPHY_API_KEY")
    if not k:
        raise RuntimeError("GIPHY_API_KEY is not configured")
    return k


def pexels_images(query: str, per_page: int = 12) -> list:
    r = requests.get(
        PEXELS_IMG,
        headers={"Authorization": _pexels_key()},
        params={"query": query, "per_page": per_page},
        timeout=30,
    )
    r.raise_for_status()
    out = []
    for p in r.json().get("photos", []):
        out.append(
            {
                "type": "image",
                "provider": "pexels",
                "url": p["src"].get("large2x") or p["src"].get("large") or p["src"].get("original"),
                "preview": p["src"].get("medium") or p["src"].get("small"),
                "title": p.get("alt") or query,
                "credit": p.get("photographer"),
            }
        )
    return out


def pexels_videos(query: str, per_page: int = 10) -> list:
    r = requests.get(
        PEXELS_VID,
        headers={"Authorization": _pexels_key()},
        params={"query": query, "per_page": per_page},
        timeout=30,
    )
    r.raise_for_status()
    out = []
    for v in r.json().get("videos", []):
        files = sorted(
            [f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4" and f.get("width")],
            key=lambda f: f["width"],
        )
        # pick smallest file with width >= 1080 else the largest available
        chosen = None
        for f in files:
            if f["width"] >= 1080:
                chosen = f
                break
        if not chosen and files:
            chosen = files[-1]
        if not chosen:
            continue
        out.append(
            {
                "type": "video",
                "provider": "pexels",
                "url": chosen["link"],
                "preview": v.get("image"),
                "title": query,
                "credit": (v.get("user") or {}).get("name"),
            }
        )
    return out


def giphy_gifs(query: str, limit: int = 15) -> list:
    r = requests.get(
        GIPHY_SEARCH,
        params={"api_key": _giphy_key(), "q": query, "limit": limit, "rating": "pg-13"},
        timeout=30,
    )
    r.raise_for_status()
    out = []
    for g in r.json().get("data", []):
        images = g.get("images", {})
        original = images.get("original", {})
        mp4 = original.get("mp4")
        gif = original.get("url")
        preview = (images.get("fixed_width") or {}).get("url") or gif
        out.append(
            {
                "type": "video" if mp4 else "gif",
                "provider": "giphy",
                "url": mp4 or gif,
                "preview": preview,
                "title": g.get("title") or query,
                "credit": (g.get("user") or {}).get("display_name"),
            }
        )
    return out


def search(kind: str, query: str) -> list:
    """kind: image | video | gif"""
    if not query:
        return []
    if kind == "image":
        return pexels_images(query)
    if kind == "video":
        return pexels_videos(query)
    if kind in ("gif", "meme"):
        return giphy_gifs(query)
    return []
