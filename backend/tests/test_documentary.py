"""Documentary mode + diagnostics + preview render tests."""
import os
import re
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
DOC_AUDIO = "/app/tests/assets/doc60.mp3"
TIMEOUT = 60


@pytest.fixture(scope="module")
def client():
    return requests.Session()


@pytest.fixture(scope="module")
def doc_job_id(client):
    with open(DOC_AUDIO, "rb") as f:
        r = client.post(
            f"{API}/jobs",
            files={"audio": ("doc60.mp3", f, "audio/mpeg")},
            data={"mode": "documentary", "format": "youtube"},
            timeout=120,
        )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _poll_ready(client, jid, deadline_s=300):
    deadline = time.time() + deadline_s
    last = None
    while time.time() < deadline:
        r = client.get(f"{API}/jobs/{jid}", timeout=TIMEOUT)
        assert r.status_code == 200
        last = r.json()
        st = last.get("status")
        if st == "ready":
            return last
        if st == "error":
            pytest.fail(f"job errored: {last.get('error')}")
        time.sleep(4)
    pytest.fail(f"timeout, last status={last.get('status') if last else 'None'}")


def _poll_done(client, jid, deadline_s=300):
    deadline = time.time() + deadline_s
    last = None
    while time.time() < deadline:
        r = client.get(f"{API}/jobs/{jid}", timeout=TIMEOUT)
        last = r.json()
        st = last.get("status")
        if st == "done" and last.get("output_ready"):
            return last
        if st == "error":
            pytest.fail(f"render errored: {last.get('error')}")
        time.sleep(4)
    pytest.fail(f"render timeout, last status={last.get('status') if last else 'None'}")


# --- Test 1: Documentary analysis + diagnostics ---
def test_documentary_analysis_and_diagnostics(client, doc_job_id):
    job = _poll_ready(client, doc_job_id, deadline_s=360)
    tl = job.get("timeline") or {}
    assert tl.get("style") == "documentary", f"style={tl.get('style')}"

    diag = tl.get("diagnostics") or {}
    assert diag, "diagnostics missing"
    cov = diag.get("visual_coverage_pct")
    assert cov is not None, "visual_coverage_pct missing"
    print(f"visual_coverage_pct={cov}")
    assert cov >= 85, f"coverage {cov}% < 85"

    # empty_visual_gaps (text_fallback) count
    text_fb = diag.get("empty_visual_gaps", diag.get("text_fallback", 0))
    print(f"text_fallback/empty_visual_gaps={text_fb}")

    giphy = diag.get("giphy_assets", 0)
    assert giphy == 0, f"documentary must have 0 giphy assets, got {giphy}"

    visuals = tl.get("visuals") or []
    assert len(visuals) > 0
    allowed_sources = {"matched", "carried", "generic", "text"}
    for v in visuals:
        assert "reason" in v, f"clip missing reason: {v}"
        assert "search_query" in v, f"clip missing search_query: {v}"
        src = v.get("source")
        assert src in allowed_sources, f"invalid source={src}: {v}"
        if src in {"matched", "carried", "generic"}:
            assert v.get("url"), f"clip source={src} missing url: {v}"
    print(f"visuals={len(visuals)}, sources={[v.get('source') for v in visuals[:12]]}")


# --- Test 2: No solid color -> non-matched clips should be source=text ---
def test_no_solid_color_only_text_fallback(client, doc_job_id):
    r = client.get(f"{API}/jobs/{doc_job_id}", timeout=TIMEOUT)
    tl = r.json()["timeline"]
    for v in tl["visuals"]:
        # no clip should have visual_type 'solid' or provider 'solid_color'
        assert v.get("visual_type") != "solid", f"solid clip: {v}"
        assert v.get("provider") != "solid_color", f"solid_color provider: {v}"
        if not v.get("url"):
            assert v.get("source") == "text", f"clip has no url and not text: {v}"


# --- Test 3: Contextual English queries ---
def test_contextual_english_queries(client, doc_job_id):
    r = client.get(f"{API}/jobs/{doc_job_id}", timeout=TIMEOUT)
    tl = r.json()["timeline"]
    queries = [v.get("search_query", "") for v in tl["visuals"] if v.get("search_query")]
    assert queries, "no queries"
    # Look for ASCII words (English) - reject queries dominated by Turkish-only chars
    turkish_only = 0
    for q in queries:
        if re.search(r"[çğıöşüÇĞİÖŞÜ]", q) and not re.search(r"[a-zA-Z]{4,}", q):
            turkish_only += 1
    ratio = turkish_only / len(queries)
    print(f"queries sample: {queries[:6]}, turkish_only_ratio={ratio}")
    assert ratio < 0.4, f"too many Turkish-only queries: {ratio}"


# --- Test 4: 60s preview render ---
def test_preview_render_60s(client, doc_job_id):
    r = client.post(f"{API}/jobs/{doc_job_id}/render", json={"preview_seconds": 60}, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    _poll_done(client, doc_job_id, deadline_s=360)

    # download redirects to R2
    dl_head = client.get(f"{API}/jobs/{doc_job_id}/download", allow_redirects=False, timeout=TIMEOUT)
    assert dl_head.status_code in (302, 307)
    loc = dl_head.headers.get("Location", "")
    assert "r2.cloudflarestorage.com" in loc, f"loc={loc}"

    dl = client.get(f"{API}/jobs/{doc_job_id}/download", timeout=180, stream=True)
    assert dl.status_code == 200
    # save to /tmp and inspect duration with ffprobe
    out_path = f"/tmp/preview_{doc_job_id}.mp4"
    with open(out_path, "wb") as f:
        for chunk in dl.iter_content(1 << 15):
            f.write(chunk)
    size = os.path.getsize(out_path)
    assert size > 100_000, f"tiny mp4 size={size}"

    import subprocess
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_name,codec_type",
         "-of", "default=noprint_wrappers=1", out_path],
        capture_output=True, text=True,
    )
    print(f"ffprobe: {probe.stdout}")
    assert "h264" in probe.stdout.lower(), f"no h264: {probe.stdout}"
    assert "aac" in probe.stdout.lower(), f"no aac: {probe.stdout}"
    m = re.search(r"duration=([\d.]+)", probe.stdout)
    assert m, "no duration"
    dur = float(m.group(1))
    print(f"preview duration={dur}s")
    assert 30 <= dur <= 75, f"expected ~60s, got {dur}"


# --- Test 5: R2 audio regression ---
def test_r2_audio_regression(client, doc_job_id):
    r = client.get(f"{API}/jobs/{doc_job_id}/audio", allow_redirects=False, timeout=TIMEOUT)
    assert r.status_code in (302, 307)
    assert "r2.cloudflarestorage.com" in r.headers.get("Location", "")
