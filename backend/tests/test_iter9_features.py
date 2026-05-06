"""Iteration 9 — LLM settings, test_llm, generate_description, OG share page."""
import os
import re
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
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def created_mix(session, auth_headers):
    payload = {
        "title": "TEST_ITER9_MIX",
        "artist": "TEST_DJ",
        "genre": "TEST_Genre",
        "bpm": 128,
        "description": "",
    }
    r = session.post(f"{API}/admin/mixes", json=payload, headers=auth_headers, timeout=30)
    assert r.status_code == 200
    mix = r.json()
    yield mix
    session.delete(f"{API}/admin/mixes/{mix['id']}", headers=auth_headers, timeout=30)


# ===== Settings GET/PATCH =====
class TestSettings:
    def test_get_settings_unauth(self, session):
        r = session.get(f"{API}/admin/settings", timeout=30)
        assert r.status_code == 401

    def test_get_settings_shape(self, session, auth_headers):
        r = session.get(f"{API}/admin/settings", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ("llm_base_url", "llm_model", "llm_enabled", "llm_api_key_set"):
            assert k in d, f"missing {k}"
        assert isinstance(d["llm_enabled"], bool)
        assert isinstance(d["llm_api_key_set"], bool)
        # Must NOT echo plaintext key
        assert "llm_api_key" not in d

    def test_patch_partial_update(self, session, auth_headers):
        r = session.patch(
            f"{API}/admin/settings",
            json={"llm_model": "TEST_MODEL_X", "llm_base_url": "http://localhost:30000/v1"},
            headers=auth_headers,
            timeout=30,
        )
        assert r.status_code == 200
        assert r.json()["llm_model"] == "TEST_MODEL_X"
        # verify persisted
        g = session.get(f"{API}/admin/settings", headers=auth_headers, timeout=30).json()
        assert g["llm_model"] == "TEST_MODEL_X"

    def test_patch_set_api_key_then_empty_preserves(self, session, auth_headers):
        # Set a key
        r = session.patch(
            f"{API}/admin/settings",
            json={"llm_api_key": "TEST_SECRET_KEY_123"},
            headers=auth_headers,
            timeout=30,
        )
        assert r.status_code == 200
        assert r.json()["llm_api_key_set"] is True

        # Empty string should preserve existing (NOT clear)
        r2 = session.patch(
            f"{API}/admin/settings",
            json={"llm_api_key": ""},
            headers=auth_headers,
            timeout=30,
        )
        assert r2.status_code == 200
        assert r2.json()["llm_api_key_set"] is True, "Empty string should preserve key"

    def test_patch_clear_api_key(self, session, auth_headers):
        # Ensure key exists
        session.patch(
            f"{API}/admin/settings",
            json={"llm_api_key": "TEST_CLEAR_ME"},
            headers=auth_headers,
            timeout=30,
        )
        # Now clear
        r = session.patch(
            f"{API}/admin/settings",
            json={"clear_api_key": True},
            headers=auth_headers,
            timeout=30,
        )
        assert r.status_code == 200
        assert r.json()["llm_api_key_set"] is False

    def test_patch_enabled_toggle(self, session, auth_headers):
        for v in (False, True):
            r = session.patch(
                f"{API}/admin/settings",
                json={"llm_enabled": v},
                headers=auth_headers,
                timeout=30,
            )
            assert r.status_code == 200
            assert r.json()["llm_enabled"] is v


# ===== test_llm endpoint =====
class TestLLMHealth:
    def test_test_llm_unauth(self, session):
        r = session.post(f"{API}/admin/settings/test_llm", timeout=30)
        assert r.status_code == 401

    def test_test_llm_returns_unreachable_error(self, session, auth_headers):
        # Make sure URL points to a definitely-unreachable LLM
        session.patch(
            f"{API}/admin/settings",
            json={
                "llm_base_url": "http://localhost:30000/v1",
                "llm_enabled": True,
            },
            headers=auth_headers,
            timeout=30,
        )
        r = session.post(f"{API}/admin/settings/test_llm", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is False
        assert "error" in d
        # Error should mention the endpoint
        assert "30000" in d["error"] or "Cannot reach" in d["error"] or "localhost" in d["error"]


# ===== generate_description endpoint =====
class TestGenerateDescription:
    def test_generate_unauth(self, session, created_mix):
        r = session.post(
            f"{API}/admin/mixes/{created_mix['id']}/generate_description",
            timeout=30,
        )
        assert r.status_code == 401

    def test_generate_unknown_mix(self, session, auth_headers):
        r = session.post(
            f"{API}/admin/mixes/nonexistent-mix-xyz/generate_description",
            headers=auth_headers,
            timeout=30,
        )
        assert r.status_code == 404

    def test_generate_returns_502_when_unreachable(self, session, auth_headers, created_mix):
        # Ensure LLM enabled + bad URL
        session.patch(
            f"{API}/admin/settings",
            json={"llm_base_url": "http://localhost:30000/v1", "llm_enabled": True},
            headers=auth_headers,
            timeout=30,
        )
        r = session.post(
            f"{API}/admin/mixes/{created_mix['id']}/generate_description",
            headers=auth_headers,
            timeout=60,
        )
        # LLM unreachable -> 502
        assert r.status_code == 502
        d = r.json()
        assert "detail" in d


# ===== /api/share/{id} OG page =====
class TestSharePage:
    def test_share_unknown_mix_404(self, session):
        r = session.get(f"{API}/share/nonexistent-share-xyz", timeout=30, allow_redirects=False)
        assert r.status_code == 404

    def test_share_returns_html_with_og_tags(self, session, created_mix):
        mid = created_mix["id"]
        r = session.get(f"{API}/share/{mid}", timeout=30, allow_redirects=False)
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "text/html" in ct
        body = r.text
        # OG tags
        assert 'property="og:title"' in body
        assert 'property="og:description"' in body
        assert 'property="og:image"' in body
        assert 'property="og:url"' in body
        # Twitter card
        assert 'name="twitter:card"' in body
        assert 'name="twitter:image"' in body
        # Meta refresh
        assert re.search(r'http-equiv="refresh"', body) is not None
        # URL contains mix id
        assert mid in body
        # Title appears
        assert "TEST_ITER9_MIX" in body

    def test_share_with_t_query(self, session, created_mix):
        mid = created_mix["id"]
        r = session.get(f"{API}/share/{mid}?t=120", timeout=30, allow_redirects=False)
        assert r.status_code == 200
        body = r.text
        # og:url and refresh URL must contain ?t=120
        m = re.search(r'property="og:url"\s+content="([^"]+)"', body)
        assert m is not None
        assert "t=120" in m.group(1)
        m2 = re.search(r'http-equiv="refresh"\s+content="0;url=([^"]+)"', body)
        assert m2 is not None
        assert "t=120" in m2.group(1)

    def test_share_fallback_to_favicon_when_no_cover(self, session, created_mix):
        # created_mix has no cover at all
        mid = created_mix["id"]
        r = session.get(f"{API}/share/{mid}", timeout=30, allow_redirects=False)
        assert r.status_code == 200
        body = r.text
        m = re.search(r'property="og:image"\s+content="([^"]+)"', body)
        assert m is not None
        og_image = m.group(1)
        # No cover -> favicon fallback
        assert "favicon" in og_image
