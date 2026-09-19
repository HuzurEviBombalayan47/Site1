"""Shitpost Studio API server."""
import os
import uuid
import random
import shutil
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from fastapi import FastAPI, APIRouter, UploadFile, File, Form, HTTPException, Body
from fastapi.responses import FileResponse, RedirectResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import logging

from providers import media
from pipeline.sfx import sfx_list, sfx_path, SFX_LIBRARY
from pipeline.timeline import FORMATS
import storage_s3 as storage
import worker

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]
jobs = db.jobs

STORAGE = Path(os.environ.get("STORAGE_DIR") or (ROOT_DIR / "storage"))
STORAGE.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Shitpost Studio")
api = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("shitpost")


@api.get("/")
async def root():
    return {"message": "Shitpost Studio API"}


@api.get("/config")
async def config():
    return {
        "providers": {
            "stt_assemblyai": bool(os.environ.get("ASSEMBLYAI_API_KEY")),
            "llm_gemini": bool(os.environ.get("GEMINI_API_KEY")),
            "pexels": bool(os.environ.get("PEXELS_API_KEY")),
            "giphy": bool(os.environ.get("GIPHY_API_KEY")),
        },
        "formats": [{"id": k, **v} for k, v in FORMATS.items()],
        "modes": [
            {"id": "documentary", "label": "Documentary", "desc": "Belgesel / video-essay, konuya uygun B-roll"},
            {"id": "normal", "label": "Normal", "desc": "Temiz YouTube edit'i"},
            {"id": "fast", "label": "Fast", "desc": "Daha fazla görsel, hızlı geçiş"},
            {"id": "shitpost", "label": "Shitpost", "desc": "Absürt meme, ani zoom, SFX"},
        ],
    }


@api.get("/sfx")
async def get_sfx():
    return {"sfx": sfx_list()}


@api.get("/sfx/{name}")
async def get_sfx_file(name: str):
    p = sfx_path(name)
    if not p.exists():
        raise HTTPException(404, "SFX not found")
    return FileResponse(str(p), media_type="audio/mpeg")


@api.get("/search")
async def search_media(kind: str, q: str):
    try:
        results = media.search(kind, q)
    except Exception as e:
        raise HTTPException(502, f"search failed: {e}")
    return {"results": results}


@api.post("/jobs")
async def create_job(
    audio: UploadFile = File(...),
    mode: str = Form("normal"),
    format: str = Form("youtube"),
):
    if mode not in ("documentary", "normal", "fast", "shitpost"):
        raise HTTPException(400, "invalid mode")
    if format not in FORMATS:
        raise HTTPException(400, "invalid format")

    job_id = str(uuid.uuid4())
    if not storage.configured():
        raise HTTPException(503, "Object storage not configured (set S3_BUCKET / S3_ACCESS_KEY_ID / S3_SECRET_ACCESS_KEY)")
    ext = Path(audio.filename or "audio.mp3").suffix or ".mp3"
    data = await audio.read()
    akey = storage.audio_key(job_id, ext)
    try:
        storage.put_bytes(akey, data, audio.content_type or "audio/mpeg")
    except Exception as e:
        raise HTTPException(502, f"upload to storage failed: {e}")

    doc = {
        "id": job_id,
        "status": "created",
        "stage": "Sıraya alındı...",
        "progress": 0,
        "mode": mode,
        "format": format,
        "audio_filename": audio.filename,
        "audio_key": akey,
        "audio_ext": ext,
        "audio_duration": None,
        "transcript": None,
        "timeline": None,
        "caption_style": None,
        "output_ready": False,
        "output_key": None,
        "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await jobs.insert_one(doc)
    worker.start_process(job_id)
    return {"id": job_id}


@api.get("/jobs/{job_id}")
async def get_job(job_id: str):
    doc = await jobs.find_one({"id": job_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "job not found")
    return doc


@api.post("/jobs/{job_id}/render")
async def render_job(job_id: str, payload: dict = Body(default={})):
    doc = await jobs.find_one({"id": job_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "job not found")
    if doc["status"] not in ("ready", "done", "error"):
        raise HTTPException(400, f"job not ready (status={doc['status']})")
    if not doc.get("timeline"):
        raise HTTPException(400, "no timeline to render")
    preview = payload.get("preview_seconds") if isinstance(payload, dict) else None
    worker.start_render(job_id, preview)
    return {"ok": True, "preview_seconds": preview}


@api.post("/jobs/{job_id}/regenerate")
async def regenerate_clip(job_id: str, payload: dict = Body(...)):
    doc = await jobs.find_one({"id": job_id}, {"_id": 0})
    if not doc or not doc.get("timeline"):
        raise HTTPException(404, "job/timeline not found")
    clip_id = payload.get("clip_id")
    new_query = payload.get("query")
    new_kind = payload.get("kind")
    visuals = doc["timeline"]["visuals"]
    clip = next((c for c in visuals if c["id"] == clip_id), None)
    if not clip:
        raise HTTPException(404, "clip not found")

    kind = new_kind or {"image": "image", "video": "video", "gif": "gif"}.get(clip.get("visual_type"), "image")
    query = new_query or clip.get("search_query") or clip.get("topic") or "abstract"
    try:
        results = media.search(kind, query)
    except Exception as e:
        raise HTTPException(502, f"search failed: {e}")
    if not results:
        raise HTTPException(404, "no media found")
    # pick a result different from current
    choices = [r for r in results if r["url"] != clip.get("url")] or results
    pick = random.choice(choices)
    clip.update({
        "url": pick["url"],
        "preview": pick.get("preview"),
        "provider": pick.get("provider"),
        "credit": pick.get("credit"),
        "visual_type": pick["type"],
        "search_query": query,
    })
    await jobs.update_one({"id": job_id}, {"$set": {"timeline.visuals": visuals}})
    return {"clip": clip}


@api.patch("/jobs/{job_id}")
async def patch_job(job_id: str, payload: dict = Body(...)):
    doc = await jobs.find_one({"id": job_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "job not found")
    updates = {}

    if "caption_style" in payload:
        updates["caption_style"] = {**(doc.get("caption_style") or {}), **payload["caption_style"]}

    timeline = doc.get("timeline") or {}
    if "clip" in payload and timeline:
        cp = payload["clip"]
        visuals = timeline["visuals"]
        for c in visuals:
            if c["id"] == cp.get("id"):
                for k in ("start", "end", "url", "preview", "effect", "visual_type", "provider", "text"):
                    if k in cp:
                        c[k] = cp[k]
        updates["timeline.visuals"] = visuals

    if "sfx" in payload and timeline:
        updates["timeline.sfx"] = payload["sfx"]

    if "captions" in payload and timeline:
        updates["timeline.captions"] = payload["captions"]

    if not updates:
        raise HTTPException(400, "nothing to update")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await jobs.update_one({"id": job_id}, {"$set": updates})
    return await jobs.find_one({"id": job_id}, {"_id": 0})


@api.get("/jobs/{job_id}/audio")
async def get_audio(job_id: str):
    doc = await jobs.find_one({"id": job_id}, {"_id": 0})
    if not doc or not doc.get("audio_key"):
        raise HTTPException(404, "audio not found")
    return RedirectResponse(storage.presigned_url(doc["audio_key"], expires=86400))


@api.get("/jobs/{job_id}/download")
async def download_video(job_id: str):
    doc = await jobs.find_one({"id": job_id}, {"_id": 0})
    if not doc or not doc.get("output_ready") or not doc.get("output_key"):
        raise HTTPException(404, "video not ready")
    return RedirectResponse(
        storage.presigned_url(doc["output_key"], expires=86400, download_name=f"shitpost_{job_id[:8]}.mp4")
    )


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
