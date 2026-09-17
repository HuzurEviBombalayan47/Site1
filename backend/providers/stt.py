"""Speech-to-Text provider (AssemblyAI). Modular: swap by implementing transcribe()."""
import os
import time
import requests

ASSEMBLYAI_BASE = "https://api.assemblyai.com/v2"


def _key():
    key = os.environ.get("ASSEMBLYAI_API_KEY")
    if not key:
        raise RuntimeError("ASSEMBLYAI_API_KEY is not configured")
    return key


def transcribe(audio_path: str, poll_timeout: int = 600) -> dict:
    """Upload a local audio file to AssemblyAI and return transcript with word timings.

    Returns: {"text": str, "words": [{"text","start","end"}], "duration": float}
    start/end are in seconds.
    """
    headers = {"authorization": _key()}

    # 1) Upload local file
    with open(audio_path, "rb") as f:
        up = requests.post(f"{ASSEMBLYAI_BASE}/upload", headers=headers, data=f, timeout=300)
    up.raise_for_status()
    upload_url = up.json()["upload_url"]

    # 2) Request transcription
    r = requests.post(
        f"{ASSEMBLYAI_BASE}/transcript",
        headers=headers,
        json={"audio_url": upload_url, "punctuate": True, "format_text": True},
        timeout=60,
    )
    r.raise_for_status()
    tid = r.json()["id"]

    # 3) Poll
    deadline = time.time() + poll_timeout
    while time.time() < deadline:
        pr = requests.get(f"{ASSEMBLYAI_BASE}/transcript/{tid}", headers=headers, timeout=60)
        pr.raise_for_status()
        data = pr.json()
        status = data.get("status")
        if status == "completed":
            words = [
                {"text": w["text"], "start": w["start"] / 1000.0, "end": w["end"] / 1000.0}
                for w in (data.get("words") or [])
            ]
            duration = data.get("audio_duration") or (words[-1]["end"] if words else 0.0)
            return {"text": data.get("text") or "", "words": words, "duration": float(duration)}
        if status == "error":
            raise RuntimeError(f"AssemblyAI error: {data.get('error')}")
        time.sleep(3)
    raise TimeoutError("AssemblyAI transcription timed out")
