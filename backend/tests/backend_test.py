"""Shitpost Studio - Backend end-to-end tests."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://soundpost-creator.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
AUDIO_PATH = "/app/tests/assets/sample_short.mp3"

TIMEOUT = 60


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    return s


# --- Config ---
def test_config(client):
    r = client.get(f"{API}/config", timeout=TIMEOUT)
    assert r.status_code == 200
    data = r.json()
    prov = data["providers"]
    assert prov["stt_assemblyai"] is True
    assert prov["llm_gemini"] is True
    assert prov["pexels"] is True
    assert prov["giphy"] is True
    assert len(data["formats"]) >= 3
    assert len(data["modes"]) >= 3


# --- SFX ---
def test_sfx_list(client):
    r = client.get(f"{API}/sfx", timeout=TIMEOUT)
    assert r.status_code == 200
    sfx = r.json()["sfx"]
    assert len(sfx) == 12, f"expected 12 sfx, got {len(sfx)}"


def test_sfx_vine_boom(client):
    r = client.get(f"{API}/sfx/vine_boom", timeout=TIMEOUT)
    assert r.status_code == 200
    assert "audio" in r.headers.get("content-type", "")


# --- Search ---
@pytest.mark.parametrize("kind", ["image", "gif", "video"])
def test_search(client, kind):
    r = client.get(f"{API}/search", params={"kind": kind, "q": "elon musk"}, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "results" in data
    assert isinstance(data["results"], list)
    assert len(data["results"]) > 0, f"no results for {kind}"


# --- Full pipeline job ---
@pytest.fixture(scope="module")
def job_id(client):
    with open(AUDIO_PATH, "rb") as f:
        r = client.post(
            f"{API}/jobs",
            files={"audio": ("sample_short.mp3", f, "audio/mpeg")},
            data={"mode": "shitpost", "format": "youtube"},
            timeout=120,
        )
    assert r.status_code == 200, r.text
    jid = r.json()["id"]
    assert jid
    return jid


def test_audio_redirect_is_r2(client, job_id):
    # Do not follow redirect - inspect 307 Location for R2 host
    r = client.get(f"{API}/jobs/{job_id}/audio", allow_redirects=False, timeout=TIMEOUT)
    assert r.status_code in (302, 307), f"expected redirect, got {r.status_code}"
    loc = r.headers.get("Location", "")
    assert "r2.cloudflarestorage.com" in loc, f"audio redirect not to R2: {loc}"
    # Follow and read a chunk to confirm bytes
    r2 = requests.get(loc, timeout=TIMEOUT, stream=True)
    assert r2.status_code == 200
    chunk = next(r2.iter_content(4096))
    assert chunk and len(chunk) > 100


def test_job_processes_to_ready(client, job_id):
    deadline = time.time() + 240
    last = None
    while time.time() < deadline:
        r = client.get(f"{API}/jobs/{job_id}", timeout=TIMEOUT)
        assert r.status_code == 200
        last = r.json()
        st = last.get("status")
        if st == "ready":
            break
        if st == "error":
            pytest.fail(f"job errored: {last}")
        time.sleep(3)
    assert last["status"] == "ready", f"status={last.get('status')}"

    # R2 storage checks: audio_key set, no legacy audio_path
    assert last.get("audio_key"), "audio_key missing"
    assert last["audio_key"].startswith("shitpost-studio/jobs/"), f"unexpected audio_key: {last['audio_key']}"
    assert "audio_path" not in last or not last.get("audio_path"), f"unexpected audio_path in job doc: {last.get('audio_path')}"

    # transcript
    tr = last.get("transcript") or {}
    assert (tr.get("text") or "").strip(), "transcript.text is empty"
    tl = last.get("timeline") or {}
    assert tl.get("used_llm") is True, f"used_llm not True: {tl.get('used_llm')}"
    visuals = tl.get("visuals") or []
    captions = tl.get("captions") or []
    assert len(visuals) > 0, "no visuals in timeline"
    for v in visuals:
        assert "start" in v and "end" in v
        assert "visual_type" in v
        assert "effect" in v
        assert "url" in v and v["url"], f"visual missing url: {v}"
    assert len(captions) > 0
    # word timings
    any_words = any(("words" in c and c["words"]) for c in captions)
    assert any_words, "no word timings on captions"


def test_regenerate(client, job_id):
    r = client.get(f"{API}/jobs/{job_id}", timeout=TIMEOUT)
    tl = r.json()["timeline"]
    clip = tl["visuals"][0]
    orig_url = clip["url"]
    r2 = client.post(f"{API}/jobs/{job_id}/regenerate", json={"clip_id": clip["id"]}, timeout=120)
    assert r2.status_code == 200, r2.text
    new_clip = r2.json().get("clip") or r2.json()
    assert new_clip.get("url"), f"regenerated clip missing url: {new_clip}"
    # url may or may not differ, but should be valid
    print(f"regenerate: orig={orig_url[:60]} new={new_clip['url'][:60]}")


def test_patch_caption_style(client, job_id):
    r = client.patch(f"{API}/jobs/{job_id}", json={"caption_style": {"size": 80}}, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    r2 = client.get(f"{API}/jobs/{job_id}", timeout=TIMEOUT)
    cs = r2.json().get("caption_style") or {}
    assert cs.get("size") == 80


def test_patch_clip_effect(client, job_id):
    r = client.get(f"{API}/jobs/{job_id}", timeout=TIMEOUT)
    clip = r.json()["timeline"]["visuals"][0]
    r2 = client.patch(f"{API}/jobs/{job_id}", json={"clip": {"id": clip["id"], "effect": "shake"}}, timeout=TIMEOUT)
    assert r2.status_code == 200, r2.text
    r3 = client.get(f"{API}/jobs/{job_id}", timeout=TIMEOUT)
    updated = next(v for v in r3.json()["timeline"]["visuals"] if v["id"] == clip["id"])
    assert updated["effect"] == "shake"


def test_patch_sfx(client, job_id):
    new_sfx = [{"id": "sfx_test1", "name": "vine_boom", "time": 1.0}]
    r = client.patch(f"{API}/jobs/{job_id}", json={"sfx": new_sfx}, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    r2 = client.get(f"{API}/jobs/{job_id}", timeout=TIMEOUT)
    sfx = r2.json()["timeline"].get("sfx") or []
    assert any(s.get("name") == "vine_boom" for s in sfx)


def test_render(client, job_id):
    r = client.post(f"{API}/jobs/{job_id}/render", timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    deadline = time.time() + 240
    last = None
    while time.time() < deadline:
        rr = client.get(f"{API}/jobs/{job_id}", timeout=TIMEOUT)
        last = rr.json()
        if last.get("status") == "done" and last.get("output_ready"):
            break
        if last.get("status") == "error":
            pytest.fail(f"render errored: {last}")
        time.sleep(3)
    assert last.get("status") == "done", f"status={last.get('status')}"
    assert last.get("output_ready") is True
    assert last.get("output_key"), "output_key missing"
    assert last["output_key"].endswith("/output.mp4")

    # Download must redirect to R2 presigned URL
    dl_head = client.get(f"{API}/jobs/{job_id}/download", allow_redirects=False, timeout=TIMEOUT)
    assert dl_head.status_code in (302, 307), f"expected redirect, got {dl_head.status_code}"
    r2loc = dl_head.headers.get("Location", "")
    assert "r2.cloudflarestorage.com" in r2loc, f"download redirect not to R2: {r2loc}"

    dl = client.get(f"{API}/jobs/{job_id}/download", timeout=120, stream=True)
    assert dl.status_code == 200
    ctype = dl.headers.get("content-type", "")
    assert "video" in ctype or "mp4" in ctype, f"content-type={ctype}"
    # read first bytes
    chunk = next(dl.iter_content(4096))
    assert chunk and len(chunk) > 100
