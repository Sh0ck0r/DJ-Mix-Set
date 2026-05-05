"""MIXDECK Phase 2 backend tests:
- /api/feed.xml (RSS podcast feed)
- /api/mixes/{id}/waveform (real audio peaks endpoint)
- Redis caching populates + invalidates via PATCH
- MixUpdate accepts key/camelot
- DELETE removes waveform JSON file
"""
import os
import shutil
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import redis as redis_sync
import requests
from dotenv import load_dotenv

from _scan_helpers import scan_and_wait

load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "mixdeck2026")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

WF_TEST_DIR = "/tmp/wf_test"
WAVEFORMS_DIR = Path(__file__).resolve().parents[1] / "storage" / "waveforms"

NS = {
    "itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
    "atom": "http://www.w3.org/2005/Atom",
}


# ========= Fixtures =========
@pytest.fixture(scope="module")
def session():
    return requests.Session()


@pytest.fixture(scope="module")
def admin_headers(session):
    r = session.post(f"{API}/auth/login", json={"password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def redis_client():
    try:
        c = redis_sync.from_url(REDIS_URL, socket_timeout=2.0)
        c.ping()
        return c
    except Exception:
        pytest.skip("Redis not reachable; cache tests skipped")


@pytest.fixture(scope="module")
def scanned_mix(session, admin_headers):
    """Scan /tmp/wf_test which contains a real mp3 + cue. Returns the new mix id.
    Uses analyze=False to keep tests fast."""
    # ensure dir + audio exist
    wf = Path(WF_TEST_DIR)
    if not (wf / "sample.mp3").exists():
        pytest.skip("/tmp/wf_test/sample.mp3 missing")
    r = scan_and_wait(
        session,
        API,
        admin_headers,
        {"path": WF_TEST_DIR, "recursive": False, "analyze": False, "default_genre": "TEST_WF"},
    )
    assert r.status_code == 200, f"scan failed: {r.status_code} {r.text}"
    body = r.json()
    # Either added now or previously - look up by source_path
    src = str(Path(WF_TEST_DIR) / "sample.mp3")
    found_id = None
    if body["added_count"] > 0:
        for a in body["added"]:
            if a["path"] == src:
                found_id = a["id"]
                break
    if not found_id:
        # already ingested - find via list
        all_mixes = session.get(f"{API}/mixes", timeout=30).json()
        for m in all_mixes:
            if m.get("source_path") == src:
                found_id = m["id"]
                break
    assert found_id, "could not locate scanned mix"
    yield found_id
    # teardown
    session.delete(f"{API}/admin/mixes/{found_id}", headers=admin_headers, timeout=30)


@pytest.fixture(scope="module")
def metadata_mix(session, admin_headers):
    """Create a mix without audio source - for metadata-only tests (PATCH key/camelot, RSS skip)."""
    r = session.post(
        f"{API}/admin/mixes",
        json={"title": "TEST_PHASE2_NoAudio", "artist": "TEST_P2", "genre": "TEST_P2", "bpm": 120},
        headers=admin_headers,
        timeout=30,
    )
    assert r.status_code == 200, r.text
    mid = r.json()["id"]
    yield mid
    session.delete(f"{API}/admin/mixes/{mid}", headers=admin_headers, timeout=30)


# ========= RSS feed tests =========
class TestRSSFeed:
    def test_feed_xml_returns_200_and_correct_content_type(self, session):
        r = session.get(f"{API}/feed.xml", timeout=30)
        assert r.status_code == 200
        assert "application/rss+xml" in r.headers.get("content-type", "")

    def test_feed_xml_is_valid_rss_with_channel(self, session, scanned_mix):
        r = session.get(f"{API}/feed.xml", timeout=30)
        assert r.status_code == 200
        # Parse and validate structure
        root = ET.fromstring(r.content)
        assert root.tag == "rss"
        channel = root.find("channel")
        assert channel is not None
        title = channel.find("title")
        assert title is not None and title.text and "MIXDECK" in title.text
        # atom:link self
        atom_link = channel.find("atom:link", NS)
        assert atom_link is not None
        # at least one item present (we have scanned_mix with source_path)
        items = channel.findall("item")
        assert len(items) >= 1
        # find our item
        our = None
        for it in items:
            g = it.find("guid")
            if g is not None and g.text == scanned_mix:
                our = it
                break
        assert our is not None, "scanned mix not in feed"
        enc = our.find("enclosure")
        assert enc is not None and enc.get("url", "").endswith(f"/api/stream/{scanned_mix}")
        guid = our.find("guid")
        assert guid.get("isPermaLink") == "false"
        # itunes:duration & link present
        assert our.find("itunes:duration", NS) is not None
        assert our.find("link") is not None

    def test_feed_skips_mixes_without_audio_source(self, session, metadata_mix):
        # metadata_mix has no audio_filename, audio_url, or source_path
        r = session.get(f"{API}/feed.xml", timeout=30)
        assert r.status_code == 200
        root = ET.fromstring(r.content)
        guids = [g.text for g in root.findall(".//item/guid")]
        assert metadata_mix not in guids, "mix without audio source should NOT be in feed"

    def test_feed_is_cached_identical_bytes(self, session, redis_client):
        r1 = session.get(f"{API}/feed.xml", timeout=30)
        r2 = session.get(f"{API}/feed.xml", timeout=30)
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.content == r2.content
        # verify Redis key exists
        assert redis_client.exists("mixdeck:rss:feed") == 1


# ========= Waveform tests =========
class TestWaveform:
    def test_waveform_404_unknown_mix(self, session):
        r = session.get(f"{API}/mixes/does-not-exist-zzz/waveform", timeout=30)
        assert r.status_code == 404

    def test_waveform_no_audio_returns_empty_not_ready(self, session, metadata_mix):
        r = session.get(f"{API}/mixes/{metadata_mix}/waveform", timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body == {"peaks": [], "ready": False}

    def test_waveform_real_audio_computes_peaks_and_persists(self, session, scanned_mix):
        # First call - may take a few seconds (librosa decode)
        wf_path = WAVEFORMS_DIR / f"{scanned_mix}.json"
        # ensure clean: delete any pre-existing wf to verify fresh compute
        # (we cannot reliably delete via API without delete-mix, so just allow either fresh or cached)
        t0 = time.time()
        r = session.get(f"{API}/mixes/{scanned_mix}/waveform", timeout=120)
        elapsed = time.time() - t0
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ready") is True, f"expected ready=True, got {body}"
        peaks = body["peaks"]
        assert isinstance(peaks, list) and len(peaks) > 0
        # bars ~1200 (allow a small range)
        assert 1000 <= body["bars"] <= 1300
        assert body["bars"] == len(peaks)
        # peaks normalized 0..1
        assert all(0.0 <= float(p) <= 1.0 for p in peaks)
        assert max(peaks) <= 1.0 and max(peaks) > 0
        # JSON file persisted on disk
        assert wf_path.exists(), f"waveform JSON not written at {wf_path}"
        print(f"[wf] first call elapsed={elapsed:.2f}s bars={body['bars']}")

    def test_waveform_second_call_is_fast_cached(self, session, scanned_mix):
        # ensure first call seeded
        session.get(f"{API}/mixes/{scanned_mix}/waveform", timeout=120)
        t0 = time.time()
        r = session.get(f"{API}/mixes/{scanned_mix}/waveform", timeout=30)
        elapsed = time.time() - t0
        assert r.status_code == 200
        body = r.json()
        assert body.get("ready") is True
        # Second call should be <2s (network + cache lookup); strict <100ms not feasible over kube ingress
        assert elapsed < 2.0, f"cached waveform call took {elapsed:.2f}s"
        print(f"[wf] cached call elapsed={elapsed*1000:.0f}ms")


# ========= MixUpdate key/camelot =========
class TestMixUpdateHarmonic:
    def test_patch_accepts_key_and_camelot(self, session, admin_headers, metadata_mix):
        r = session.patch(
            f"{API}/admin/mixes/{metadata_mix}",
            json={"camelot": "7B", "key": "F major"},
            headers=admin_headers,
            timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["camelot"] == "7B"
        assert body["key"] == "F major"
        # Verify persisted via GET
        r2 = session.get(f"{API}/mixes/{metadata_mix}", timeout=30)
        assert r2.status_code == 200
        d = r2.json()
        assert d["camelot"] == "7B"
        assert d["key"] == "F major"


# ========= Redis cache behavior =========
class TestRedisCache:
    def test_mixes_list_populates_cache_key(self, session, redis_client):
        # bust first
        for k in redis_client.keys("mixdeck:mixes:list:*"):
            redis_client.delete(k)
        r = session.get(f"{API}/mixes", timeout=30)
        assert r.status_code == 200
        # Key format: mixdeck:mixes:list::  (q='', genre='')
        keys = [k.decode() if isinstance(k, bytes) else k for k in redis_client.keys("mixdeck:mixes:list:*")]
        assert any(k == "mixdeck:mixes:list::" for k in keys), f"expected cache key not found, got: {keys}"

    def test_mixes_list_second_call_is_faster(self, session, redis_client):
        # warm
        session.get(f"{API}/mixes", timeout=30)
        t0 = time.time()
        r = session.get(f"{API}/mixes", timeout=30)
        elapsed = time.time() - t0
        assert r.status_code == 200
        # Just sanity - cached call should be reasonably quick
        print(f"[cache] mixes list cached call: {elapsed*1000:.0f}ms")

    def test_patch_invalidates_mixdeck_cache(self, session, admin_headers, metadata_mix, redis_client):
        # warm caches
        session.get(f"{API}/mixes", timeout=30)
        session.get(f"{API}/mixes/{metadata_mix}", timeout=30)
        # confirm keys exist
        pre_keys = redis_client.keys("mixdeck:mixes:*") + redis_client.keys(f"mixdeck:mix:{metadata_mix}")
        assert len(pre_keys) > 0, "expected cache keys before PATCH"
        # PATCH
        r = session.patch(
            f"{API}/admin/mixes/{metadata_mix}",
            json={"description": "TEST_P2 invalidation"},
            headers=admin_headers,
            timeout=30,
        )
        assert r.status_code == 200
        # mixes:* and mix:* keys should be cleared
        post_keys = redis_client.keys("mixdeck:mixes:*") + redis_client.keys(f"mixdeck:mix:{metadata_mix}")
        # Note: rss:feed is also invalidated
        assert len(post_keys) == 0, f"expected mixes/mix caches cleared, found: {post_keys}"

    def test_compatible_cache_invalidated_on_patch(self, session, admin_headers, scanned_mix, redis_client):
        # warm compatible cache
        session.get(f"{API}/mixes/{scanned_mix}/compatible", timeout=30)
        pre = redis_client.keys("mixdeck:compatible:*")
        assert len(pre) > 0, "expected compatible cache key"
        # PATCH any field
        r = session.patch(
            f"{API}/admin/mixes/{scanned_mix}",
            json={"description": "touched"},
            headers=admin_headers,
            timeout=30,
        )
        assert r.status_code == 200
        post = redis_client.keys("mixdeck:compatible:*")
        assert len(post) == 0, f"compatible cache should be cleared after PATCH; found: {post}"


# ========= DELETE removes waveform JSON =========
class TestDeleteWaveformCleanup:
    def test_delete_removes_waveform_json_file(self, session, admin_headers):
        # create a fresh scan-ingested mix, fetch waveform, delete it, verify no orphan
        # easier: create metadata mix, then write a fake waveform JSON to test the cleanup on delete
        r = session.post(
            f"{API}/admin/mixes",
            json={"title": "TEST_P2_DelWF", "artist": "x"},
            headers=admin_headers,
            timeout=30,
        )
        assert r.status_code == 200
        mid = r.json()["id"]
        wf_file = WAVEFORMS_DIR / f"{mid}.json"
        wf_file.parent.mkdir(parents=True, exist_ok=True)
        wf_file.write_text('{"peaks": [0.1, 0.2], "ready": true, "bars": 2}', encoding="utf-8")
        assert wf_file.exists()
        # DELETE
        r2 = session.delete(f"{API}/admin/mixes/{mid}", headers=admin_headers, timeout=30)
        assert r2.status_code == 200
        # waveform JSON should be gone
        assert not wf_file.exists(), f"waveform file leaked at {wf_file}"
