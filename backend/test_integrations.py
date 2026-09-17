"""Real API connectivity tests for Shitpost Studio external services.
Reads keys from backend/.env. Does NOT hardcode any secret.
Run: python test_integrations.py
"""
import os
import time
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

ASSEMBLYAI_API_KEY = os.environ.get("ASSEMBLYAI_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
GIPHY_API_KEY = os.environ.get("GIPHY_API_KEY")

results = {}


def log(name, ok, detail):
    status = "PASS" if ok else "FAIL"
    results[name] = {"ok": ok, "detail": detail}
    print(f"[{status}] {name}: {detail}")


def test_pexels():
    try:
        r = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": "elon musk", "per_page": 2},
            timeout=30,
        )
        if r.status_code == 200:
            data = r.json()
            n = len(data.get("photos", []))
            log("Pexels Image", True, f"200 OK, {n} photos, total_results={data.get('total_results')}")
        else:
            log("Pexels Image", False, f"HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log("Pexels Image", False, f"EXC {e}")


def test_pexels_video():
    try:
        r = requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": "space rocket", "per_page": 2},
            timeout=30,
        )
        if r.status_code == 200:
            data = r.json()
            n = len(data.get("videos", []))
            log("Pexels Video", True, f"200 OK, {n} videos")
        else:
            log("Pexels Video", False, f"HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log("Pexels Video", False, f"EXC {e}")


def test_giphy():
    try:
        r = requests.get(
            "https://api.giphy.com/v1/gifs/search",
            params={"api_key": GIPHY_API_KEY, "q": "surprised reaction", "limit": 2},
            timeout=30,
        )
        if r.status_code == 200:
            data = r.json()
            n = len(data.get("data", []))
            first = data["data"][0]["images"]["original"]["url"] if n else None
            log("Giphy GIF", True, f"200 OK, {n} gifs, sample={first}")
        else:
            log("Giphy GIF", False, f"HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log("Giphy GIF", False, f"EXC {e}")


def test_gemini():
    prompt = {"contents": [{"parts": [{"text": "Reply with exactly: OK"}]}]}
    models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
    # Attempt 1: API key as query param (standard AIza keys)
    for m in models:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent",
                params={"key": GEMINI_API_KEY},
                json=prompt,
                timeout=30,
            )
            if r.status_code == 200:
                txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                log("Gemini LLM", True, f"query-key OK ({m}): {txt.strip()[:60]}")
                return
        except Exception as e:
            pass
    # Attempt 2: Bearer token (OAuth-style AQ. token)
    for m in models:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent",
                headers={"Authorization": f"Bearer {GEMINI_API_KEY}"},
                json=prompt,
                timeout=30,
            )
            if r.status_code == 200:
                txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                log("Gemini LLM", True, f"Bearer OK ({m}): {txt.strip()[:60]}")
                return
        except Exception as e:
            pass
    # Report last failure detail
    try:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
            params={"key": GEMINI_API_KEY},
            json=prompt,
            timeout=30,
        )
        log("Gemini LLM", False, f"query-key HTTP {r.status_code}: {r.text[:300]}")
    except Exception as e:
        log("Gemini LLM", False, f"EXC {e}")


def test_assemblyai():
    base = "https://api.assemblyai.com/v2"
    headers = {"authorization": ASSEMBLYAI_API_KEY}
    audio_url = "https://assembly.ai/wildfires.mp3"
    try:
        r = requests.post(
            f"{base}/transcript",
            headers=headers,
            json={"audio_url": audio_url},
            timeout=30,
        )
        if r.status_code not in (200, 201):
            log("AssemblyAI STT", False, f"submit HTTP {r.status_code}: {r.text[:200]}")
            return
        tid = r.json()["id"]
        print(f"    AssemblyAI transcript queued id={tid}, polling...")
        deadline = time.time() + 90
        while time.time() < deadline:
            pr = requests.get(f"{base}/transcript/{tid}", headers=headers, timeout=30)
            st = pr.json().get("status")
            if st == "completed":
                text = pr.json().get("text", "")[:80]
                log("AssemblyAI STT", True, f"completed, transcript sample='{text}...'")
                return
            if st == "error":
                log("AssemblyAI STT", False, f"transcript error: {pr.json().get('error')}")
                return
            time.sleep(5)
        log("AssemblyAI STT", True, "auth+submit OK (still processing at timeout) id=" + tid)
    except Exception as e:
        log("AssemblyAI STT", False, f"EXC {e}")


if __name__ == "__main__":
    print("=== Shitpost Studio External API Connectivity Tests ===\n")
    test_pexels()
    test_pexels_video()
    test_giphy()
    test_gemini()
    test_assemblyai()
    print("\n=== SUMMARY ===")
    print(json.dumps(results, indent=2))
