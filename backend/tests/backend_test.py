"""MIXDECK backend API tests."""
import os
import io
import uuid
import pytest
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
ADMIN_PASSWORD = "mixdeck2026"

SAMPLE_CUE = """PERFORMER "DJ TEST"
TITLE "TEST MIX"
FILE "mix.mp3" MP3
  TRACK 01 AUDIO
    TITLE "Track One"
    PERFORMER "Artist A"
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    TITLE "Track Two"
    PERFORMER "Artist B"
    INDEX 01 03:45:00
  TRACK 03 AUDIO
    TITLE "Track Three"
    INDEX 01 08:12:30
"""


# ========= Fixtures =========
@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    return s


@pytest.fixture(scope="session")
def admin_token(session):
    r = session.post(f"{API}/auth/login", json={"password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="session")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def created_mix(session, auth_headers):
    payload = {
        "title": "TEST_MIX_Alpha",
        "artist": "TEST_Artist",
        "genre": "TEST_Genre",
        "bpm": 128,
        "description": "TEST mix for regression",
    }
    r = session.post(f"{API}/admin/mixes", json=payload, headers=auth_headers, timeout=30)
    assert r.status_code == 200, f"create failed: {r.status_code} {r.text}"
    mix = r.json()
    yield mix
    # teardown
    try:
        session.delete(f"{API}/admin/mixes/{mix['id']}", headers=auth_headers, timeout=30)
    except Exception:
        pass


# ========= Root / seed =========
class TestRoot:
    def test_root(self, session):
        r = session.get(f"{API}/", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "message" in data
        assert "version" in data

    def test_seed_demo(self, session):
        r = session.post(f"{API}/seed-demo", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True
        # first call returns id OR skipped=true if seeded already by previous runs
        # second call here verifies idempotency
        r2 = session.post(f"{API}/seed-demo", timeout=30)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2.get("skipped") is True
        assert d2.get("count", 0) >= 1


# ========= Auth =========
class TestAuth:
    def test_login_success(self, session):
        r = session.post(f"{API}/auth/login", json={"password": ADMIN_PASSWORD}, timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json().get("token"), str)

    def test_login_wrong_password(self, session):
        r = session.post(f"{API}/auth/login", json={"password": "wrong"}, timeout=30)
        assert r.status_code == 401

    def test_verify_without_token(self, session):
        r = session.get(f"{API}/auth/verify", timeout=30)
        assert r.status_code == 401

    def test_verify_with_invalid_token(self, session):
        r = session.get(
            f"{API}/auth/verify",
            headers={"Authorization": "Bearer invalid.jwt.token"},
            timeout=30,
        )
        assert r.status_code == 401

    def test_verify_with_valid_token(self, session, auth_headers):
        r = session.get(f"{API}/auth/verify", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        assert r.json().get("valid") is True


# ========= Admin protection =========
class TestAdminProtection:
    def test_create_requires_auth(self, session):
        r = session.post(f"{API}/admin/mixes", json={"title": "nope"}, timeout=30)
        assert r.status_code == 401

    def test_patch_requires_auth(self, session):
        r = session.patch(f"{API}/admin/mixes/xxx", json={"title": "nope"}, timeout=30)
        assert r.status_code == 401

    def test_delete_requires_auth(self, session):
        r = session.delete(f"{API}/admin/mixes/xxx", timeout=30)
        assert r.status_code == 401

    def test_audio_upload_requires_auth(self, session):
        r = session.post(
            f"{API}/admin/mixes/xxx/audio",
            files={"file": ("f.mp3", b"x", "audio/mpeg")},
            timeout=30,
        )
        assert r.status_code == 401


# ========= Mix CRUD + list =========
class TestMixes:
    def test_list_mixes_no_mongo_id(self, session):
        r = session.get(f"{API}/mixes", timeout=30)
        assert r.status_code == 200
        mixes = r.json()
        assert isinstance(mixes, list)
        for m in mixes:
            assert "_id" not in m
            assert "id" in m

    def test_get_genres(self, session):
        r = session.get(f"{API}/mixes/genres", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "genres" in data
        assert isinstance(data["genres"], list)

    def test_create_and_get_mix(self, session, created_mix):
        mid = created_mix["id"]
        assert "_id" not in created_mix
        assert created_mix["title"] == "TEST_MIX_Alpha"
        assert created_mix["bpm"] == 128

        r = session.get(f"{API}/mixes/{mid}", timeout=30)
        assert r.status_code == 200
        got = r.json()
        assert got["id"] == mid
        assert got["title"] == "TEST_MIX_Alpha"
        assert "_id" not in got

    def test_genre_visible(self, session, created_mix):
        r = session.get(f"{API}/mixes/genres", timeout=30)
        assert r.status_code == 200
        assert "TEST_Genre" in r.json()["genres"]

    def test_patch_mix(self, session, auth_headers, created_mix):
        mid = created_mix["id"]
        r = session.patch(
            f"{API}/admin/mixes/{mid}",
            json={"description": "updated desc", "bpm": 130},
            headers=auth_headers,
            timeout=30,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["description"] == "updated desc"
        assert data["bpm"] == 130
        # verify persisted
        r2 = session.get(f"{API}/mixes/{mid}", timeout=30)
        assert r2.json()["description"] == "updated desc"

    def test_play_count_increment(self, session, created_mix):
        mid = created_mix["id"]
        before = session.get(f"{API}/mixes/{mid}", timeout=30).json()["play_count"]
        r = session.post(f"{API}/mixes/{mid}/play", timeout=30)
        assert r.status_code == 200
        after = session.get(f"{API}/mixes/{mid}", timeout=30).json()["play_count"]
        assert after == before + 1

    def test_play_nonexistent(self, session):
        r = session.post(f"{API}/mixes/nonexistent-id-xyz/play", timeout=30)
        assert r.status_code == 404

    def test_get_nonexistent(self, session):
        r = session.get(f"{API}/mixes/nonexistent-id-xyz", timeout=30)
        assert r.status_code == 404

    def test_public_duration_sets_when_zero(self, session, auth_headers):
        # create a fresh mix
        r = session.post(
            f"{API}/admin/mixes",
            json={"title": "TEST_DurationMix"},
            headers=auth_headers,
            timeout=30,
        )
        mid = r.json()["id"]
        try:
            assert session.get(f"{API}/mixes/{mid}").json()["duration"] == 0.0
            r2 = session.post(
                f"{API}/mixes/{mid}/duration", data={"duration": "321.5"}, timeout=30
            )
            assert r2.status_code == 200
            assert session.get(f"{API}/mixes/{mid}").json()["duration"] == 321.5

            # second call should NOT overwrite
            r3 = session.post(
                f"{API}/mixes/{mid}/duration", data={"duration": "999.9"}, timeout=30
            )
            assert r3.status_code == 200
            assert session.get(f"{API}/mixes/{mid}").json()["duration"] == 321.5
        finally:
            session.delete(f"{API}/admin/mixes/{mid}", headers=auth_headers, timeout=30)


# ========= File uploads + CUE parsing + streaming =========
class TestUploadsAndStreaming:
    def test_cue_upload_and_parse(self, session, auth_headers, created_mix):
        mid = created_mix["id"]
        files = {"file": ("test.cue", SAMPLE_CUE.encode("utf-8"), "text/plain")}
        r = session.post(
            f"{API}/admin/mixes/{mid}/cue", files=files, headers=auth_headers, timeout=30
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["track_count"] == 3
        tracks = data["tracks"]
        assert tracks[0]["title"] == "Track One"
        assert tracks[0]["artist"] == "Artist A"
        assert tracks[0]["start_seconds"] == 0.0
        assert tracks[1]["title"] == "Track Two"
        assert tracks[1]["artist"] == "Artist B"
        assert tracks[1]["start_seconds"] == 225.0
        assert tracks[2]["title"] == "Track Three"
        assert abs(tracks[2]["start_seconds"] - 492.4) < 0.01

        # verify persisted on mix
        mix = session.get(f"{API}/mixes/{mid}", timeout=30).json()
        assert len(mix["tracks"]) == 3
        assert mix["tracks"][1]["start_seconds"] == 225.0

    def test_audio_upload_and_stream_range(self, session, auth_headers, created_mix):
        mid = created_mix["id"]
        # ~1MB dummy payload
        payload = b"\xFF\xFB\x90\x00" + os.urandom(1024 * 1024 - 4)
        files = {"file": ("track.mp3", payload, "audio/mpeg")}
        r = session.post(
            f"{API}/admin/mixes/{mid}/audio",
            files=files,
            headers=auth_headers,
            timeout=60,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["filename"].endswith(".mp3")

        # verify audio_filename persisted
        mix = session.get(f"{API}/mixes/{mid}", timeout=30).json()
        assert mix["audio_filename"] == data["filename"]

        # Range request 1: first 1024 bytes
        r1 = session.get(
            f"{API}/stream/{mid}", headers={"Range": "bytes=0-1023"}, timeout=30
        )
        assert r1.status_code == 206
        assert r1.headers.get("Accept-Ranges") == "bytes"
        cr = r1.headers.get("Content-Range", "")
        assert cr.startswith("bytes 0-1023/")
        assert len(r1.content) == 1024

        # Range request 2: bytes=1024-
        r2 = session.get(
            f"{API}/stream/{mid}", headers={"Range": "bytes=1024-"}, timeout=60
        )
        assert r2.status_code == 206
        cr2 = r2.headers.get("Content-Range", "")
        assert cr2.startswith("bytes 1024-")
        assert r2.headers.get("Accept-Ranges") == "bytes"

    def test_cover_upload_and_fetch(self, session, auth_headers, created_mix):
        mid = created_mix["id"]
        # minimal 1x1 PNG
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8"
            b"\xcf\xc0\x00\x00\x00\x03\x00\x01\x5b\xd9\xc3\xa6\x00\x00\x00\x00"
            b"IEND\xaeB`\x82"
        )
        files = {"file": ("cover.png", png, "image/png")}
        r = session.post(
            f"{API}/admin/mixes/{mid}/cover",
            files=files,
            headers=auth_headers,
            timeout=30,
        )
        assert r.status_code == 200, r.text
        assert r.json()["filename"].endswith(".png")

        r2 = session.get(f"{API}/cover/{mid}", timeout=30)
        assert r2.status_code == 200
        assert r2.headers.get("content-type", "").startswith("image/")
        assert len(r2.content) > 0


# ========= Delete =========
class TestDelete:
    def test_delete_mix_removes(self, session, auth_headers):
        # Fresh mix for delete
        r = session.post(
            f"{API}/admin/mixes",
            json={"title": "TEST_ToDelete"},
            headers=auth_headers,
            timeout=30,
        )
        mid = r.json()["id"]
        d = session.delete(
            f"{API}/admin/mixes/{mid}", headers=auth_headers, timeout=30
        )
        assert d.status_code == 200
        assert d.json().get("ok") is True
        g = session.get(f"{API}/mixes/{mid}", timeout=30)
        assert g.status_code == 404
