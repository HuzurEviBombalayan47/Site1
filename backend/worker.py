"""Background worker (threaded, sync pymongo) for transcription/analysis and rendering."""
import os
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).parent / ".env")

from providers import stt
from pipeline import analyze, render
from pipeline.timeline import default_caption_style

_client = MongoClient(os.environ["MONGO_URL"])
_db = _client[os.environ["DB_NAME"]]
_jobs = _db.jobs

STORAGE = Path(os.environ.get("STORAGE_DIR") or (Path(__file__).parent / "storage"))


def _update(job_id: str, **fields):
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    _jobs.update_one({"id": job_id}, {"$set": fields})


def _get(job_id: str):
    return _jobs.find_one({"id": job_id}, {"_id": 0})


def process_job(job_id: str):
    try:
        job = _get(job_id)
        audio_path = Path(job["audio_path"])
        _update(job_id, status="transcribing", stage="Ses analiz ediliyor...", progress=10)
        tr = stt.transcribe(str(audio_path))
        _update(
            job_id,
            transcript={"text": tr["text"], "words": tr["words"]},
            audio_duration=tr["duration"],
            status="analyzing",
            stage="Konular belirleniyor...",
            progress=40,
        )
        tl = analyze.build_timeline(
            tr["words"], tr["duration"], job["mode"], job["format"],
            log=lambda m: _update(job_id, stage=m),
        )
        _update(
            job_id,
            timeline=tl,
            caption_style=default_caption_style(),
            status="ready",
            stage="Editör hazır",
            progress=100,
        )
    except Exception as e:
        traceback.print_exc()
        _update(job_id, status="error", stage="Hata", error=str(e)[:500])


def render_job(job_id: str):
    try:
        _update(job_id, status="rendering", stage="Render başlıyor...", progress=0, output_ready=False)
        job = _get(job_id)
        job_dir = STORAGE / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        audio_path = Path(job["audio_path"])

        def cb(pct, stage):
            _update(job_id, progress=int(pct), stage=stage)

        out = render.render_timeline(job, job_dir, audio_path, cb)
        _update(job_id, status="done", output_ready=True, output_path=str(out),
                stage="Video hazır", progress=100)
    except Exception as e:
        traceback.print_exc()
        _update(job_id, status="error", stage="Render hatası", error=str(e)[:800])


def start_process(job_id: str):
    threading.Thread(target=process_job, args=(job_id,), daemon=True).start()


def start_render(job_id: str):
    threading.Thread(target=render_job, args=(job_id,), daemon=True).start()
