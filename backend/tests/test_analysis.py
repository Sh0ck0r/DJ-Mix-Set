"""MIXDECK backend: BPM + key analysis + Discogs tier-3 fallback tests."""
import os
import re
import shutil
import time
import pytest
import requests
from pathlib import Path
from dotenv import load_dotenv

from _scan_helpers import scan_and_wait

load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
ADMIN_PASSWORD = "mixdeck2026"

REAL_AUDIO = Path("/tmp/real_audio.mp3")
SCAN_ROOT = Path("/tmp/mixdeck_analyze_test")

CUE_CONTENT = """PERFORMER "DJ ANALYSIS"
TITLE "ANALYSIS TEST MIX"
FILE "real_audio.mp3" MP3
  TRACK 01 AUDIO
    TITLE "Analysis Track One"
    PERFORMER "Test Artist"
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    TITLE "Analysis Track Two"
    PERFORMER "Test Artist"
    INDEX 01 00:18:00
"""


@pytest.fixture(scope="module")
def session():
    return requests.Session()


@pytest.fixture(scope="module")
def auth(session):
    r = session.post(f"{API}/auth/login", json={"password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def scan_dir():
    assert REAL_AUDIO.exists(), f"{REAL_AUDIO} missing"
    if SCAN_ROOT.exists():
        shutil.rmtree(SCAN_ROOT)
    SCAN_ROOT.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REAL_AUDIO, SCAN_ROOT / "real_audio.mp3")
    (SCAN_ROOT / "real_audio.cue").write_text(CUE_CONTENT, encoding="utf-8")
    yield SCAN_ROOT


@pytest.fixture(scope="module", autouse=True)
def cleanup(session):
    yield
    try:
        r = session.post(f"{API}/auth/login", json={"password": ADMIN_PASSWORD}, timeout=15)
        if r.status_code == 200:
            hdr = {"Authorization": f"Bearer {r.json()['token']}"}
            mixes = session.get(f"{API}/mixes", timeout=15).json()
            for m in mixes:
                sp = m.get("source_path") or ""
                if str(SCAN_ROOT) in sp:
                    session.delete(f"{API}/admin/mixes/{m['id']}", headers=hdr, timeout=15)
    finally:
        if SCAN_ROOT.exists():
            shutil.rmtree(SCAN_ROOT, ignore_errors=True)


def test_analyze_requires_admin(session):
    r = session.post(f"{API}/admin/mixes/fake-id/analyze", timeout=15)
    assert r.status_code == 401


def test_analysis_status_public_404(session):
    r = session.get(f"{API}/mixes/nonexistent-xyz/analysis_status", timeout=15)
    assert r.status_code == 404


def test_scan_analyze_false_does_not_queue(session, auth, scan_dir):
    r = scan_and_wait(
        session,
        API,
        auth,
        {"path": str(scan_dir), "recursive": False, "analyze": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["added_count"] == 1
    assert body["analysis_queued"] == 0, body
    mix_id = body["added"][0]["id"]
    st = session.get(f"{API}/mixes/{mix_id}/analysis_status", timeout=15).json()
    assert st["status"] == "none"
    session.delete(f"{API}/admin/mixes/{mix_id}", headers=auth, timeout=15)


def test_scan_analyze_true_runs_end_to_end(session, auth, scan_dir):
    r = scan_and_wait(
        session,
        API,
        auth,
        {"path": str(scan_dir), "recursive": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["added_count"] == 1
    assert body["analysis_queued"] == 1, body
    mix_id = body["added"][0]["id"]
    pytest.analysis_mix_id = mix_id

    deadline = time.time() + 60
    final_status = None
    data = {}
    while time.time() < deadline:
        r = session.get(f"{API}/mixes/{mix_id}/analysis_status", timeout=15)
        assert r.status_code == 200
        data = r.json()
        final_status = data["status"]
        if final_status in ("done", "failed"):
            break
        time.sleep(2)

    assert final_status == "done", f"analysis status: {final_status}"
    assert "bpm" in data and "key" in data and "camelot" in data

    mix = session.get(f"{API}/mixes/{mix_id}", timeout=15).json()
    assert mix["analysis_status"] == "done"
    assert len(mix["tracks"]) == 2
    t0 = mix["tracks"][0]
    assert isinstance(t0.get("bpm"), int) and t0["bpm"] > 0, f"track0 bpm: {t0}"
    assert t0.get("key"), f"track0 key: {t0}"
    cam = t0.get("camelot") or ""
    assert re.match(r"^\d{1,2}[AB]$", cam), f"invalid camelot: {cam!r}"


def test_rescan_does_not_requeue(session, auth, scan_dir):
    r = scan_and_wait(
        session,
        API,
        auth,
        {"path": str(scan_dir), "recursive": False},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["added_count"] == 0
    assert body["skipped_count"] == 1
    assert body["analysis_queued"] == 0


def test_analyze_endpoint_response(session, auth):
    mix_id = pytest.analysis_mix_id
    r = session.post(f"{API}/admin/mixes/{mix_id}/analyze", headers=auth, timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert data.get("status") in ("pending", "already_running")


def test_analyze_endpoint_404(session, auth):
    r = session.post(f"{API}/admin/mixes/nope-xyz/analyze", headers=auth, timeout=15)
    assert r.status_code == 404


def test_artwork_chain_with_empty_discogs(session):
    r = session.get(
        f"{API}/tracks/artwork",
        params={"artist": "Aly & Fila", "title": "It's All About The Melody", "refresh": 1},
        timeout=30,
    )
    assert r.status_code == 200
    data = r.json()
    assert "url" in data and "source" in data and "cached" in data
    assert data["source"] == "itunes", f"expected itunes, got {data}"
    assert data["url"]
    assert data["cached"] is False


def test_artwork_unknown_returns_no_crash(session):
    r = session.get(
        f"{API}/tracks/artwork",
        params={
            "artist": "TESTARTIST_ZXQWV_NONEXISTENT_9988",
            "title": "TESTTITLE_ZXQWV_NONEXISTENT_9988",
            "refresh": 1,
        },
        timeout=30,
    )
    assert r.status_code == 200
    data = r.json()
    assert "url" in data and "source" in data
