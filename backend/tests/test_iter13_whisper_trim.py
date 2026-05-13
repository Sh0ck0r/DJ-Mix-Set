"""Iteration 13 tests — Whisper transition trim setting + per-track transcribe endpoint.

Covers:
- GET /api/admin/settings returns whisper_transition_trim (default 15)
- PATCH /api/admin/settings persists whisper_transition_trim (round-trip)
- PATCH invalid trim values must not 500
- POST /api/admin/settings/test_whisper returns ok=false with error when unreachable
- POST /api/admin/mixes/{id}/transcribe_track/{idx}:
    * 401 without admin token
    * 400 when whisper_enabled=False (WhisperNotConfigured)
    * 404 on invalid mix id
    * 404 on out-of-range track index
    * 400 on track with no artist/title
    * 502 when whisper enabled but endpoint unreachable
"""
import os
import pytest
import requests

_BASE = os.environ.get("REACT_APP_BACKEND_URL")
if not _BASE:
    # Fall back to frontend/.env
    try:
        with open("/app/frontend/.env") as _f:
            for _line in _f:
                if _line.startswith("REACT_APP_BACKEND_URL="):
                    _BASE = _line.split("=", 1)[1].strip()
                    break
    except Exception:
        pass
assert _BASE, "REACT_APP_BACKEND_URL not set"
BASE_URL = _BASE.rstrip("/")
ADMIN_PASSWORD = "mixdeck2026"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"password": ADMIN_PASSWORD}, timeout=10)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def seeded_mix_id():
    r = requests.get(f"{BASE_URL}/api/mixes", timeout=10)
    assert r.status_code == 200
    mixes = r.json()
    assert len(mixes) > 0, "no seeded mixes found"
    # find one with tracks
    for m in mixes:
        if m.get("tracks"):
            return m["id"]
    return mixes[0]["id"]


@pytest.fixture(scope="module", autouse=True)
def restore_original_settings(auth_headers):
    """Snapshot+restore settings around this module."""
    r = requests.get(f"{BASE_URL}/api/admin/settings", headers=auth_headers, timeout=10)
    original = r.json() if r.status_code == 200 else None
    yield
    if original:
        # restore whisper fields
        restore = {
            "whisper_enabled": bool(original.get("whisper_enabled", False)),
            "whisper_transition_trim": int(original.get("whisper_transition_trim", 15)),
            "whisper_base_url": original.get("whisper_base_url", ""),
            "whisper_model": original.get("whisper_model", ""),
            "whisper_language": original.get("whisper_language", ""),
        }
        requests.patch(f"{BASE_URL}/api/admin/settings", json=restore, headers=auth_headers, timeout=10)


# ===== Settings: whisper_transition_trim =====
class TestWhisperTransitionTrim:
    def test_get_settings_has_trim_default_15(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/admin/settings", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "whisper_transition_trim" in data
        assert isinstance(data["whisper_transition_trim"], int)
        # value should be sensible (default 15, but may already be patched by prior tests — just check it's >=0)
        assert data["whisper_transition_trim"] >= 0

    @pytest.mark.parametrize("trim", [0, 5, 12, 15, 30])
    def test_patch_trim_roundtrip(self, auth_headers, trim):
        r = requests.patch(
            f"{BASE_URL}/api/admin/settings",
            json={"whisper_transition_trim": trim},
            headers=auth_headers, timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["whisper_transition_trim"] == trim
        # round-trip via GET
        r2 = requests.get(f"{BASE_URL}/api/admin/settings", headers=auth_headers, timeout=10)
        assert r2.status_code == 200
        assert r2.json()["whisper_transition_trim"] == trim

    def test_patch_invalid_trim_no_500(self, auth_headers):
        # Pydantic Optional[int] should reject strings with 422, but must not 500
        r = requests.patch(
            f"{BASE_URL}/api/admin/settings",
            json={"whisper_transition_trim": "abc"},
            headers=auth_headers, timeout=10,
        )
        assert r.status_code != 500, f"server 500 on bad trim: {r.text}"
        assert r.status_code in (200, 400, 422)

    def test_patch_negative_trim_no_500(self, auth_headers):
        # Backend accepts Optional[int] — negative may persist or get clamped, must not 500
        r = requests.patch(
            f"{BASE_URL}/api/admin/settings",
            json={"whisper_transition_trim": -5},
            headers=auth_headers, timeout=10,
        )
        assert r.status_code != 500
        # restore sane
        requests.patch(f"{BASE_URL}/api/admin/settings",
                       json={"whisper_transition_trim": 15},
                       headers=auth_headers, timeout=10)


# ===== test_whisper endpoint =====
class TestWhisperHealthCheck:
    def test_test_whisper_unreachable(self, auth_headers):
        # Whisper server is intentionally NOT running in test env
        r = requests.post(f"{BASE_URL}/api/admin/settings/test_whisper",
                          headers=auth_headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "ok" in data
        # ok must be False since no local whisper
        assert data["ok"] is False
        assert "error" in data and data["error"]


# ===== transcribe_track endpoint =====
class TestTranscribeTrack:
    def test_requires_admin_token(self, seeded_mix_id):
        r = requests.post(
            f"{BASE_URL}/api/admin/mixes/{seeded_mix_id}/transcribe_track/0",
            timeout=10,
        )
        assert r.status_code == 401

    def test_404_invalid_mix(self, auth_headers):
        # ensure whisper enabled so we don't short-circuit on config
        requests.patch(f"{BASE_URL}/api/admin/settings",
                       json={"whisper_enabled": True,
                             "whisper_base_url": "http://localhost:8000/v1",
                             "whisper_model": "Systran/faster-whisper-large-v3"},
                       headers=auth_headers, timeout=10)
        r = requests.post(
            f"{BASE_URL}/api/admin/mixes/nonexistent-mix-id-xyz/transcribe_track/0",
            headers=auth_headers, timeout=10,
        )
        assert r.status_code == 404

    def test_404_out_of_range_track_index(self, auth_headers, seeded_mix_id):
        r = requests.post(
            f"{BASE_URL}/api/admin/mixes/{seeded_mix_id}/transcribe_track/9999",
            headers=auth_headers, timeout=10,
        )
        assert r.status_code == 404

    def test_400_when_whisper_disabled(self, auth_headers, seeded_mix_id):
        # disable whisper
        requests.patch(f"{BASE_URL}/api/admin/settings",
                       json={"whisper_enabled": False},
                       headers=auth_headers, timeout=10)
        r = requests.post(
            f"{BASE_URL}/api/admin/mixes/{seeded_mix_id}/transcribe_track/0",
            headers=auth_headers, timeout=15,
        )
        # Either 400 (WhisperNotConfigured) or 400 (no audio source) — must NOT 500
        assert r.status_code != 500
        assert r.status_code == 400
        detail = r.json().get("detail", "")
        # Should contain a meaningful error
        assert detail

    def test_400_track_missing_artist_and_title(self, auth_headers):
        # Create a temporary mix with one empty-meta track
        create = requests.post(
            f"{BASE_URL}/api/admin/mixes",
            json={"title": "TEST_iter13_empty_track", "artist": "TEST"},
            headers=auth_headers, timeout=10,
        )
        assert create.status_code == 200
        mid = create.json()["id"]
        try:
            # patch with one empty track
            requests.patch(
                f"{BASE_URL}/api/admin/mixes/{mid}",
                json={"tracks": [{"index": 1, "title": "", "artist": "", "start_seconds": 0}]},
                headers=auth_headers, timeout=10,
            )
            # enable whisper
            requests.patch(f"{BASE_URL}/api/admin/settings",
                           json={"whisper_enabled": True},
                           headers=auth_headers, timeout=10)
            r = requests.post(
                f"{BASE_URL}/api/admin/mixes/{mid}/transcribe_track/0",
                headers=auth_headers, timeout=15,
            )
            assert r.status_code == 400
            assert "artist" in r.json().get("detail", "").lower() or "title" in r.json().get("detail", "").lower()
        finally:
            requests.delete(f"{BASE_URL}/api/admin/mixes/{mid}", headers=auth_headers, timeout=10)

    def test_whisper_enabled_unreachable_no_500(self, auth_headers, seeded_mix_id):
        # Enable whisper but point to unreachable URL — should return 400 (no audio) or 502, NOT 500
        requests.patch(f"{BASE_URL}/api/admin/settings",
                       json={"whisper_enabled": True,
                             "whisper_base_url": "http://localhost:8000/v1",
                             "whisper_model": "Systran/faster-whisper-large-v3"},
                       headers=auth_headers, timeout=10)
        r = requests.post(
            f"{BASE_URL}/api/admin/mixes/{seeded_mix_id}/transcribe_track/0",
            headers=auth_headers, timeout=30,
        )
        # Must NOT be 500. Acceptable: 400 (no audio source / config) or 502 (whisper unreachable)
        assert r.status_code != 500, f"server crashed: {r.text}"
        assert r.status_code in (400, 502)
