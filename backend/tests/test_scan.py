"""MIXDECK backend: bulk directory scan tests.

Tests POST /api/admin/scan and source_path fallback behavior of
/api/stream/{id}, /api/cover/{id}, and DELETE /api/admin/mixes/{id}.
"""
import os
import shutil
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

from _scan_helpers import scan_and_wait

load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
ADMIN_PASSWORD = "mixdeck2026"

# Root scan directory - unique per run to avoid collision with other iterations
SCAN_ROOT = Path("/tmp/mixdeck_scan_test")

CUE_CONTENT_WITH_PERFORMER = """PERFORMER "DJ SCAN HEADER"
TITLE "SCAN TEST MIX A"
FILE "mix_a.mp3" MP3
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

# Empty PERFORMER at header level to confirm empty-artist fix
CUE_CONTENT_EMPTY_PERFORMER = """PERFORMER ""
TITLE "SCAN TEST MIX B"
FILE "mix_b.mp3" MP3
  TRACK 01 AUDIO
    TITLE "Solo"
    PERFORMER "X"
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    TITLE "Pair"
    INDEX 01 02:30:00
"""

# Subfolder CUE (for recursive test)
CUE_CONTENT_SUBFOLDER = """PERFORMER "DJ SUB"
TITLE "SCAN TEST SUB MIX"
FILE "sub_mix.mp3" MP3
  TRACK 01 AUDIO
    TITLE "Sub Track"
    INDEX 01 00:00:00
"""

# Fake MP3 bytes (~256 bytes) - content only needs to be readable for streaming
FAKE_MP3 = b"ID3\x03\x00\x00\x00\x00\x00\x00" + (b"\xff\xfb\x90\x00" * 64)
# 1x1 PNG for cover
FAKE_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0\x00\x00\x00"
    b"\x03\x00\x01\x5b\xda\x7f\x0f\x00\x00\x00\x00IEND\xaeB`\x82"
)


# ========= Fixtures =========
@pytest.fixture(scope="module")
def session():
    return requests.Session()


@pytest.fixture(scope="module")
def admin_token(session):
    r = session.post(f"{API}/auth/login", json={"password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def scan_dir():
    """Set up test directory structure:

    SCAN_ROOT/
      mix_a.mp3
      mix_a.cue        (with TITLE + PERFORMER)
      cover.jpg        (sibling cover)
      mix_b.mp3
      mix_b.cue        (empty PERFORMER "")
      orphan.mp3       (no cue, no cover - fallback to filename stem)
      sub/
        sub_mix.mp3
        sub_mix.cue
    """
    if SCAN_ROOT.exists():
        shutil.rmtree(SCAN_ROOT)
    SCAN_ROOT.mkdir(parents=True, exist_ok=True)
    sub = SCAN_ROOT / "sub"
    sub.mkdir(parents=True, exist_ok=True)

    (SCAN_ROOT / "mix_a.mp3").write_bytes(FAKE_MP3)
    (SCAN_ROOT / "mix_a.cue").write_text(CUE_CONTENT_WITH_PERFORMER, encoding="utf-8")
    (SCAN_ROOT / "cover.jpg").write_bytes(FAKE_PNG)

    (SCAN_ROOT / "mix_b.mp3").write_bytes(FAKE_MP3)
    (SCAN_ROOT / "mix_b.cue").write_text(CUE_CONTENT_EMPTY_PERFORMER, encoding="utf-8")

    (SCAN_ROOT / "orphan.mp3").write_bytes(FAKE_MP3)

    (sub / "sub_mix.mp3").write_bytes(FAKE_MP3)
    (sub / "sub_mix.cue").write_text(CUE_CONTENT_SUBFOLDER, encoding="utf-8")

    yield SCAN_ROOT
    # teardown handled at end of module by cleanup fixture


@pytest.fixture(scope="module", autouse=True)
def cleanup(session, request):
    """Remove any TEST-prefixed source_path mixes after tests complete."""
    yield
    # delete all mixes that were created from our scan root so DB is clean
    try:
        r = session.post(f"{API}/auth/login", json={"password": ADMIN_PASSWORD}, timeout=15)
        if r.status_code == 200:
            tok = r.json()["token"]
            hdr = {"Authorization": f"Bearer {tok}"}
            mixes = session.get(f"{API}/mixes", timeout=15).json()
            for m in mixes:
                sp = m.get("source_path") or ""
                if str(SCAN_ROOT) in sp:
                    session.delete(f"{API}/admin/mixes/{m['id']}", headers=hdr, timeout=15)
    finally:
        if SCAN_ROOT.exists():
            shutil.rmtree(SCAN_ROOT, ignore_errors=True)


# ========= Auth =========
def test_scan_requires_admin(session):
    r = session.post(f"{API}/admin/scan", json={"path": "/tmp"}, timeout=15)
    assert r.status_code == 401


def test_scan_bad_path_returns_400(session, auth):
    r = session.post(
        f"{API}/admin/scan",
        json={"path": "/tmp/definitely_does_not_exist_xyz123"},
        headers=auth,
        timeout=15,
    )
    assert r.status_code == 400
    body = r.json()
    assert "detail" in body and body["detail"]


# ========= Scan behavior =========
def test_scan_recursive_ingests_all(session, auth, scan_dir):
    r = scan_and_wait(
        session,
        API,
        auth,
        {"path": str(scan_dir), "recursive": True, "default_genre": "TEST_Scan"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # 4 audio files: mix_a, mix_b, orphan, sub/sub_mix
    assert body["scanned"] == 4, body
    assert body["added_count"] == 4
    assert body["skipped_count"] == 0
    assert body["failed_count"] == 0
    assert body["root"] == str(scan_dir)

    by_path = {a["path"]: a for a in body["added"]}

    # mix_a: cue + cover + 3 tracks, artist from cue PERFORMER
    a = by_path[str(scan_dir / "mix_a.mp3")]
    assert a["cue"] is True
    assert a["cover"] is True
    assert a["tracks"] == 3
    assert a["title"] == "SCAN TEST MIX A"
    assert a["artist"] == "DJ SCAN HEADER"

    # mix_b: empty PERFORMER "" must yield empty artist (NOT stray quote)
    b = by_path[str(scan_dir / "mix_b.mp3")]
    assert b["cue"] is True
    assert b["tracks"] == 2
    assert b["title"] == "SCAN TEST MIX B"
    assert b["artist"] == "", f"empty PERFORMER should give empty artist, got: {b['artist']!r}"

    # orphan: no cue -> title from stem, no tracks.
    # cover IS expected because generic cover.jpg sits in same folder.
    o = by_path[str(scan_dir / "orphan.mp3")]
    assert o["cue"] is False
    assert o["tracks"] == 0
    assert o["cover"] is True  # picks up shared cover.jpg via generic name
    assert o["title"] == "orphan"
    assert o["artist"] == ""

    # sub_mix: recursive descent
    sub_key = str(scan_dir / "sub" / "sub_mix.mp3")
    s = by_path[sub_key]
    assert s["cue"] is True
    assert s["tracks"] == 1
    assert s["title"] == "SCAN TEST SUB MIX"

    # Verify DB persistence + source_path/source_cover_path
    full_a = session.get(f"{API}/mixes/{a['id']}", timeout=15).json()
    assert full_a["source_path"] == str(scan_dir / "mix_a.mp3")
    assert full_a["source_cover_path"] == str(scan_dir / "cover.jpg")
    assert full_a["genre"] == "TEST_Scan"
    assert len(full_a["tracks"]) == 3
    assert full_a["tracks"][0]["title"] == "Track One"
    assert full_a["tracks"][1]["start_seconds"] == 225.0  # 3:45

    # mix_b source_cover_path - cover.jpg is same folder, detected as generic "cover"
    full_b = session.get(f"{API}/mixes/{b['id']}", timeout=15).json()
    assert full_b["source_path"] == str(scan_dir / "mix_b.mp3")
    # cover.jpg in SCAN_ROOT is a generic name — mix_b should also pick it up
    assert full_b["source_cover_path"] == str(scan_dir / "cover.jpg")

    # sub has NO cover sibling
    full_s = session.get(f"{API}/mixes/{s['id']}", timeout=15).json()
    assert full_s["source_cover_path"] in (None, "", )

    # Save ids on the module for later tests
    pytest.scan_ids = {"a": a["id"], "b": b["id"], "orphan": o["id"], "sub": s["id"]}


def test_scan_idempotent(session, auth, scan_dir):
    # Re-run same scan; expect all 4 skipped
    r = scan_and_wait(
        session,
        API,
        auth,
        {"path": str(scan_dir), "recursive": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["added_count"] == 0
    assert body["skipped_count"] == 4
    for entry in body["skipped"]:
        assert entry["reason"] == "already_ingested"


def test_scan_non_recursive_skips_subfolders(session, auth, scan_dir):
    # Clean out all existing scan mixes first so we can observe non-recursive counts
    mixes = session.get(f"{API}/mixes", timeout=15).json()
    for m in mixes:
        sp = m.get("source_path") or ""
        if str(scan_dir) in sp:
            session.delete(f"{API}/admin/mixes/{m['id']}", headers=auth, timeout=15)

    r = scan_and_wait(
        session,
        API,
        auth,
        {"path": str(scan_dir), "recursive": False},
    )
    assert r.status_code == 200
    body = r.json()
    # Only top-level mp3s: mix_a, mix_b, orphan -> 3 (NOT sub/sub_mix)
    assert body["scanned"] == 3, body
    assert body["added_count"] == 3
    paths = [a["path"] for a in body["added"]]
    assert all("sub" not in Path(p).parent.name for p in paths), paths
    # Store id of mix_a for next streaming tests
    a_id = next(a["id"] for a in body["added"] if a["path"].endswith("mix_a.mp3"))
    pytest.scan_mix_a_id = a_id


# ========= Streaming & Cover for source_path mix =========
def test_stream_source_path_range(session):
    mix_id = pytest.scan_mix_a_id
    # Full request
    r = session.get(f"{API}/stream/{mix_id}", timeout=15)
    assert r.status_code == 200
    assert r.headers.get("Accept-Ranges") == "bytes"
    full_len = int(r.headers.get("Content-Length") or len(r.content))
    assert full_len > 0

    # Range request
    r2 = session.get(f"{API}/stream/{mix_id}", headers={"Range": "bytes=0-99"}, timeout=15)
    assert r2.status_code == 206
    cr = r2.headers.get("Content-Range") or ""
    assert cr.startswith("bytes 0-99/")
    assert r2.headers.get("Accept-Ranges") == "bytes"
    assert int(r2.headers.get("Content-Length")) == 100


def test_cover_source_path(session):
    mix_id = pytest.scan_mix_a_id
    r = session.get(f"{API}/cover/{mix_id}", timeout=15)
    assert r.status_code == 200
    ct = r.headers.get("content-type", "")
    assert ct.startswith("image/"), ct
    assert len(r.content) > 0


# ========= Delete must NOT remove source file on disk =========
def test_delete_preserves_source_files(session, auth, scan_dir):
    mix_id = pytest.scan_mix_a_id
    audio_src = scan_dir / "mix_a.mp3"
    cue_src = scan_dir / "mix_a.cue"
    cover_src = scan_dir / "cover.jpg"
    assert audio_src.exists() and cue_src.exists() and cover_src.exists()

    r = session.delete(f"{API}/admin/mixes/{mix_id}", headers=auth, timeout=15)
    assert r.status_code == 200
    # Verify DB record gone
    g = session.get(f"{API}/mixes/{mix_id}", timeout=15)
    assert g.status_code == 404
    # CRITICAL: source files must still be on disk
    assert audio_src.exists(), "DELETE removed the user's source audio file!"
    assert cue_src.exists(), "DELETE removed the user's source cue file!"
    assert cover_src.exists(), "DELETE removed the user's source cover file!"
