"""SFX library metadata. Files live in backend/assets/sfx/."""
from pathlib import Path

SFX_DIR = Path(__file__).resolve().parent.parent / "assets" / "sfx"

SFX_LIBRARY = {
    "vine_boom": {"label": "Vine Boom", "category": "impact", "mood": "sudden emphasis / reveal"},
    "whoosh": {"label": "Whoosh", "category": "transition", "mood": "fast movement / transition"},
    "pop": {"label": "Pop", "category": "cartoon", "mood": "light pop / appear"},
    "record_scratch": {"label": "Record Scratch", "category": "comedy", "mood": "wait what / stop"},
    "bass_drop": {"label": "Bass Drop", "category": "impact", "mood": "hype / drop"},
    "error": {"label": "Error", "category": "ui", "mood": "wrong / fail"},
    "dramatic_hit": {"label": "Dramatic Hit", "category": "impact", "mood": "dramatic reveal"},
    "click": {"label": "Click", "category": "ui", "mood": "click / tick"},
    "notification": {"label": "Notification", "category": "ui", "mood": "ding / alert"},
    "explosion": {"label": "Explosion", "category": "impact", "mood": "boom / chaos"},
    "airhorn": {"label": "Airhorn", "category": "hype", "mood": "hype / celebration"},
    "boing": {"label": "Boing", "category": "cartoon", "mood": "cartoon bounce / silly"},
}


def sfx_names():
    return list(SFX_LIBRARY.keys())


def sfx_path(name: str) -> Path:
    return SFX_DIR / f"{name}.mp3"


def sfx_list():
    return [
        {"name": n, **meta, "url": f"/api/sfx/{n}"}
        for n, meta in SFX_LIBRARY.items()
        if sfx_path(n).exists()
    ]
