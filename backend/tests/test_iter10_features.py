"""Iteration 10 — Long-mix optimization features:
1. GET /api/mixes ?tag= filter + AND with ?q=
2. GET /api/mixes/tags (sorted by count DESC)
3. POST /api/admin/mixes/{id}/generate_tags (502 since LLM unreachable, 401, 404, 400)
4. PATCH /api/admin/mixes/{id} accepts `tags` array (persists, cache invalidated)
"""
import os
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
def two_mixes(session, auth_headers):
    """Create two mixes with distinct tag sets, yield, then cleanup."""
    created = []
    for i in range(2):
        payload = {
            "title": f"TEST_ITER10_MIX_{i}",
            "artist": "TEST_DJ_ITER10",
            "genre": "TEST_Genre_Iter10",
            "bpm": 128 + i,
            "description": "",
        }
        r = session.post(f"{API}/admin/mixes", json=payload, headers=auth_headers, timeout=30)
        assert r.status_code == 200, r.text
        created.append(r.json())
    yield created
    for m in created:
        session.delete(f"{API}/admin/mixes/{m['id']}", headers=auth_headers, timeout=30)


# ================== /api/mixes ?tag= filter ==================
class TestMixesTagFilter:
    def test_mixes_no_tag_returns_all(self, session, two_mixes):
        r = session.get(f"{API}/mixes", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        ids = {m["id"] for m in data}
        for tm in two_mixes:
            assert tm["id"] in ids

    def test_patch_tags_then_filter_by_tag(self, session, auth_headers, two_mixes):
        m1, m2 = two_mixes
        # Plant distinct tags
        r1 = session.patch(
            f"{API}/admin/mixes/{m1['id']}",
            json={"tags": ["test-iter10-uplifting", "test-iter10-shared"]},
            headers=auth_headers,
            timeout=30,
        )
        assert r1.status_code == 200, r1.text
        assert sorted(r1.json()["tags"]) == sorted(["test-iter10-uplifting", "test-iter10-shared"])

        r2 = session.patch(
            f"{API}/admin/mixes/{m2['id']}",
            json={"tags": ["test-iter10-dark", "test-iter10-shared"]},
            headers=auth_headers,
            timeout=30,
        )
        assert r2.status_code == 200, r2.text

        # Filter by unique tag → only m1
        r = session.get(f"{API}/mixes", params={"tag": "test-iter10-uplifting"}, timeout=30)
        assert r.status_code == 200
        ids = {m["id"] for m in r.json()}
        assert m1["id"] in ids
        assert m2["id"] not in ids

        # Filter by other unique tag → only m2
        r = session.get(f"{API}/mixes", params={"tag": "test-iter10-dark"}, timeout=30)
        assert r.status_code == 200
        ids = {m["id"] for m in r.json()}
        assert m2["id"] in ids
        assert m1["id"] not in ids

        # Filter by shared tag → both
        r = session.get(f"{API}/mixes", params={"tag": "test-iter10-shared"}, timeout=30)
        assert r.status_code == 200
        ids = {m["id"] for m in r.json()}
        assert m1["id"] in ids and m2["id"] in ids

    def test_filter_unknown_tag_returns_empty(self, session, two_mixes):
        r = session.get(f"{API}/mixes", params={"tag": "no-such-tag-test-iter10-zzzz"}, timeout=30)
        assert r.status_code == 200
        assert r.json() == []

    def test_q_and_tag_combined_AND(self, session, two_mixes):
        m1, _ = two_mixes
        # Title matches m1 only AND tag is shared (matches both) → m1 only
        r = session.get(
            f"{API}/mixes",
            params={"q": "TEST_ITER10_MIX_0", "tag": "test-iter10-shared"},
            timeout=30,
        )
        assert r.status_code == 200
        ids = {m["id"] for m in r.json()}
        assert m1["id"] in ids
        assert len(ids) == 1

        # Mismatched combo → empty
        r = session.get(
            f"{API}/mixes",
            params={"q": "TEST_ITER10_MIX_0", "tag": "test-iter10-dark"},
            timeout=30,
        )
        assert r.status_code == 200
        assert r.json() == []

    def test_clear_tags_with_empty_array(self, session, auth_headers, two_mixes):
        m1, _ = two_mixes
        r = session.patch(
            f"{API}/admin/mixes/{m1['id']}",
            json={"tags": []},
            headers=auth_headers,
            timeout=30,
        )
        assert r.status_code == 200
        assert r.json()["tags"] == []
        # Verify cache invalidated and filter no longer returns m1
        r2 = session.get(f"{API}/mixes", params={"tag": "test-iter10-uplifting"}, timeout=30)
        assert r2.status_code == 200
        ids = {m["id"] for m in r2.json()}
        assert m1["id"] not in ids
        # Restore for following tests
        session.patch(
            f"{API}/admin/mixes/{m1['id']}",
            json={"tags": ["test-iter10-uplifting", "test-iter10-shared"]},
            headers=auth_headers,
            timeout=30,
        )


# ================== /api/mixes/tags ==================
class TestTagsEndpoint:
    def test_tags_endpoint_shape_and_sort(self, session, two_mixes):
        r = session.get(f"{API}/mixes/tags", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "tags" in d
        assert isinstance(d["tags"], list)
        # shared tag should have count 2 if both mixes still have it
        by_tag = {row["tag"]: row["count"] for row in d["tags"]}
        if "test-iter10-shared" in by_tag:
            assert by_tag["test-iter10-shared"] >= 2
        # validate sort by count desc
        counts = [row["count"] for row in d["tags"]]
        assert counts == sorted(counts, reverse=True)
        # Each row has correct shape
        for row in d["tags"]:
            assert "tag" in row and "count" in row
            assert isinstance(row["tag"], str)
            assert isinstance(row["count"], int)


# ================== generate_tags endpoint ==================
class TestGenerateTags:
    def test_generate_tags_unauth(self, session, two_mixes):
        r = session.post(
            f"{API}/admin/mixes/{two_mixes[0]['id']}/generate_tags",
            timeout=30,
        )
        assert r.status_code == 401

    def test_generate_tags_unknown_mix_404(self, session, auth_headers):
        r = session.post(
            f"{API}/admin/mixes/nonexistent-iter10-xyz/generate_tags",
            headers=auth_headers,
            timeout=30,
        )
        assert r.status_code == 404

    def test_generate_tags_502_when_llm_unreachable(self, session, auth_headers, two_mixes):
        # Ensure LLM enabled + bad URL
        session.patch(
            f"{API}/admin/settings",
            json={"llm_base_url": "http://localhost:30000/v1", "llm_enabled": True},
            headers=auth_headers,
            timeout=30,
        )
        r = session.post(
            f"{API}/admin/mixes/{two_mixes[0]['id']}/generate_tags",
            headers=auth_headers,
            timeout=60,
        )
        assert r.status_code == 502, f"expected 502, got {r.status_code}: {r.text}"
        d = r.json()
        assert "detail" in d

    def test_generate_tags_400_when_llm_disabled(self, session, auth_headers, two_mixes):
        # Disable LLM
        r = session.patch(
            f"{API}/admin/settings",
            json={"llm_enabled": False},
            headers=auth_headers,
            timeout=30,
        )
        assert r.status_code == 200
        try:
            r = session.post(
                f"{API}/admin/mixes/{two_mixes[0]['id']}/generate_tags",
                headers=auth_headers,
                timeout=60,
            )
            assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"
            d = r.json()
            assert "detail" in d
        finally:
            # Re-enable
            session.patch(
                f"{API}/admin/settings",
                json={"llm_enabled": True},
                headers=auth_headers,
                timeout=30,
            )


# ================== PATCH tags persistence + cache invalidation ==================
class TestPatchTagsPersistence:
    def test_patch_tags_persists_via_get_mix(self, session, auth_headers, two_mixes):
        m1 = two_mixes[0]
        new_tags = ["persist-tag-a", "persist-tag-b"]
        r = session.patch(
            f"{API}/admin/mixes/{m1['id']}",
            json={"tags": new_tags},
            headers=auth_headers,
            timeout=30,
        )
        assert r.status_code == 200
        # Verify via GET /api/mixes/{id}
        g = session.get(f"{API}/mixes/{m1['id']}", timeout=30)
        assert g.status_code == 200
        assert sorted(g.json().get("tags", [])) == sorted(new_tags)

    def test_cache_invalidated_after_patch(self, session, auth_headers, two_mixes):
        m1 = two_mixes[0]
        unique = "iter10-cache-bust-xyz"
        # Set a unique tag
        session.patch(
            f"{API}/admin/mixes/{m1['id']}",
            json={"tags": [unique]},
            headers=auth_headers,
            timeout=30,
        )
        # Filter should immediately reflect
        r = session.get(f"{API}/mixes", params={"tag": unique}, timeout=30)
        assert r.status_code == 200
        ids = {m["id"] for m in r.json()}
        assert m1["id"] in ids
        # Now change tags to remove unique
        session.patch(
            f"{API}/admin/mixes/{m1['id']}",
            json={"tags": ["other-tag-iter10"]},
            headers=auth_headers,
            timeout=30,
        )
        r2 = session.get(f"{API}/mixes", params={"tag": unique}, timeout=30)
        assert r2.status_code == 200
        ids2 = {m["id"] for m in r2.json()}
        assert m1["id"] not in ids2
