"""Iteration 12 — Synced lyrics via LRCLIB.net

Features tested:
1. GET  /api/tracks/lyrics?artist=&title=  (LRCLIB fetch, MongoDB cache, negative-cache, refresh)
2. POST /api/admin/tracks/lyrics  (manual override + LRC parser edge cases via API)
3. Local LRC parser unit tests (multi-timestamp, section labels, no-ts lines)
"""
import os
import time
import pytest
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
ADMIN_PASSWORD = "mixdeck2026"


@pytest.fixture(scope="module")
def session():
    return requests.Session()


@pytest.fixture(scope="module")
def auth_headers(session):
    r = session.post(f"{API}/auth/login", json={"password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


# ============ GET /api/tracks/lyrics — public ============
class TestLyricsPublic:
    def test_yellow_synced_returns_found(self, session):
        r = session.get(f"{API}/tracks/lyrics",
                        params={"artist": "Coldplay", "title": "Yellow"}, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["found"] is True, data
        assert data["source"] == "lrclib"
        assert isinstance(data["synced"], list)
        assert len(data["synced"]) > 5, f"Expected > 5 synced lines for Yellow, got {len(data['synced'])}"
        # Each entry has time + text
        for e in data["synced"][:3]:
            assert "time" in e and "text" in e
            assert isinstance(e["time"], (int, float))

    def test_yellow_cached_on_repeat(self, session):
        # First call (warmup; could be cached: bool either way)
        session.get(f"{API}/tracks/lyrics",
                    params={"artist": "Coldplay", "title": "Yellow"}, timeout=30)
        # Second call must come from cache
        r = session.get(f"{API}/tracks/lyrics",
                        params={"artist": "Coldplay", "title": "Yellow"}, timeout=30)
        assert r.status_code == 200
        assert r.json()["cached"] is True

    def test_sun_and_moon_trance_track(self, session):
        r = session.get(f"{API}/tracks/lyrics",
                        params={"artist": "Above & Beyond", "title": "Sun & Moon"}, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["found"] is True, data
        assert isinstance(data["synced"], list)
        assert len(data["synced"]) > 0

    def test_nonexistent_track_negative_cache(self, session):
        # First call: should hit upstream and miss
        r1 = session.get(f"{API}/tracks/lyrics",
                         params={"artist": "nonexistent12345", "title": "fakefakefake"}, timeout=30)
        assert r1.status_code == 200, r1.text  # NOT 404
        d1 = r1.json()
        assert d1["found"] is False
        assert d1["synced"] == []
        assert d1["plain"] == ""
        assert d1["source"] is None
        # Second call: must come from negative cache
        r2 = session.get(f"{API}/tracks/lyrics",
                         params={"artist": "nonexistent12345", "title": "fakefakefake"}, timeout=30)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["found"] is False
        assert d2["cached"] is True

    def test_refresh_bypasses_cache(self, session):
        # Prime the cache
        session.get(f"{API}/tracks/lyrics",
                    params={"artist": "Coldplay", "title": "Yellow"}, timeout=30)
        r = session.get(f"{API}/tracks/lyrics",
                        params={"artist": "Coldplay", "title": "Yellow", "refresh": 1}, timeout=30)
        assert r.status_code == 200
        # refresh=1 bypasses cache → cached should be False
        assert r.json()["cached"] is False

    def test_empty_artist_and_title_short_circuits(self, session):
        r = session.get(f"{API}/tracks/lyrics",
                        params={"artist": "", "title": ""}, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["found"] is False
        assert data["synced"] == []
        assert data["source"] is None


# ============ POST /api/admin/tracks/lyrics — manual override ============
class TestLyricsManual:
    def test_manual_requires_auth(self, session):
        r = session.post(f"{API}/admin/tracks/lyrics",
                         json={"artist": "X", "title": "Y", "plain": "hi", "synced": ""}, timeout=30)
        assert r.status_code in (401, 403)

    def test_manual_parses_lrc(self, session, auth_headers):
        body = {
            "artist": "TEST_ITER12",
            "title": "TEST_MANUAL",
            "plain": "Hello\nWorld",
            "synced": "[00:01.50]Hello\n[00:05.00]World",
        }
        r = session.post(f"{API}/admin/tracks/lyrics", json=body,
                         headers=auth_headers, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["source"] == "manual"
        assert data["found"] is True
        assert data["synced"] == [
            {"time": 1.5, "text": "Hello"},
            {"time": 5.0, "text": "World"},
        ]

    def test_manual_400_when_empty(self, session, auth_headers):
        body = {"artist": "", "title": "", "plain": "", "synced": ""}
        r = session.post(f"{API}/admin/tracks/lyrics", json=body,
                         headers=auth_headers, timeout=30)
        assert r.status_code == 400

    def test_manual_multi_timestamp_line(self, session, auth_headers):
        body = {
            "artist": "TEST_ITER12_MULTI",
            "title": "TEST_MULTI_TS",
            "synced": "[00:01.00][00:02.50]Same text\n[00:10.00]Other",
        }
        r = session.post(f"{API}/admin/tracks/lyrics", json=body,
                         headers=auth_headers, timeout=30)
        assert r.status_code == 200
        synced = r.json()["synced"]
        # Two entries for "Same text" at 1.0 and 2.5, plus one for "Other"
        same_text_entries = [e for e in synced if e["text"] == "Same text"]
        assert len(same_text_entries) == 2
        times = sorted(e["time"] for e in same_text_entries)
        assert times == [1.0, 2.5]
        assert any(e["text"] == "Other" and e["time"] == 10.0 for e in synced)

    def test_manual_section_labels_ignored(self, session, auth_headers):
        # [Verse 1] and lines without timestamps must NOT appear as lyric entries.
        body = {
            "artist": "TEST_ITER12_LABEL",
            "title": "TEST_LABEL",
            "synced": "[Verse 1]\nNo timestamp here\n[00:03.00]Real line",
        }
        r = session.post(f"{API}/admin/tracks/lyrics", json=body,
                         headers=auth_headers, timeout=30)
        assert r.status_code == 200
        synced = r.json()["synced"]
        texts = [e["text"] for e in synced]
        # Should contain only the real line
        assert "Real line" in texts
        assert "No timestamp here" not in texts
        # No section label leaked through ([Verse 1] is parsed as [00:Verse 1] which won't match)
        assert all(t != "" for t in texts)


# ============ LRC parser unit tests (in-process import) ============
class TestLrcParser:
    def test_parse_basic(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from lyrics_service import parse_lrc
        out = parse_lrc("[00:01.50]Hello\n[00:05.00]World")
        assert out == [{"time": 1.5, "text": "Hello"}, {"time": 5.0, "text": "World"}]

    def test_parse_multi_timestamps(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from lyrics_service import parse_lrc
        out = parse_lrc("[00:01.00][00:02.50]Same\n[00:10.00]Other")
        # Two entries for Same, one for Other
        same = [e for e in out if e["text"] == "Same"]
        assert len(same) == 2

    def test_parse_ignores_no_timestamp(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from lyrics_service import parse_lrc
        out = parse_lrc("No timestamp here\n[00:03.00]Real")
        assert len(out) == 1
        assert out[0]["text"] == "Real"
