"""Iteration 11 — Bulk LLM ops + Embed + Tag-overlap compatible scoring.

Features tested:
1. POST /api/admin/llm/auto_tag_all (auth, disabled-state, force flag)
2. POST /api/admin/llm/auto_describe_all
3. GET  /api/admin/llm/bulk/{task_id}  (full state shape, failure path with unreachable LLM)
4. GET  /api/admin/llm/bulk            (list)
5. Skipping logic: skips already-tagged/described unless force=true
6. GET  /api/embed/{mix_id}            (HTML player iframe)
7. /api/mixes/{id}/compatible          tag-overlap scoring + cache invalidation on PATCH tags
"""
import os
import time
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
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _wait_for_done(session, auth_headers, task_id, timeout=60):
    """Poll /bulk/{task_id} until status != 'running' or timeout."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = session.get(f"{API}/admin/llm/bulk/{task_id}", headers=auth_headers, timeout=30)
        if r.status_code != 200:
            return r.status_code, None
        last = r.json()
        if last.get("status") != "running":
            return 200, last
        time.sleep(1.0)
    return 200, last  # timeout — return whatever we have


@pytest.fixture(scope="module")
def ensure_llm_enabled(session, auth_headers):
    """Make sure LLM is enabled (it's the iter10 final state, but be defensive)."""
    r = session.patch(
        f"{API}/admin/settings",
        json={"llm_enabled": True, "llm_base_url": "http://localhost:30000/v1"},
        headers=auth_headers,
        timeout=30,
    )
    assert r.status_code == 200
    yield
    # Restore (idempotent)
    session.patch(
        f"{API}/admin/settings",
        json={"llm_enabled": True, "llm_base_url": "http://localhost:30000/v1"},
        headers=auth_headers,
        timeout=30,
    )


# ============== Bulk endpoints: auth + shape ==============
class TestBulkAuth:
    def test_auto_tag_all_requires_auth(self, session):
        r = session.post(f"{API}/admin/llm/auto_tag_all", timeout=30)
        assert r.status_code in (401, 403)

    def test_auto_describe_all_requires_auth(self, session):
        r = session.post(f"{API}/admin/llm/auto_describe_all", timeout=30)
        assert r.status_code in (401, 403)

    def test_bulk_status_requires_auth(self, session):
        r = session.get(f"{API}/admin/llm/bulk/anything", timeout=30)
        assert r.status_code in (401, 403)

    def test_list_bulk_requires_auth(self, session):
        r = session.get(f"{API}/admin/llm/bulk", timeout=30)
        assert r.status_code in (401, 403)


class TestBulkDisabledLLM:
    def test_auto_tag_all_400_when_disabled(self, session, auth_headers):
        # Disable
        r = session.patch(f"{API}/admin/settings", json={"llm_enabled": False},
                          headers=auth_headers, timeout=30)
        assert r.status_code == 200
        try:
            r = session.post(f"{API}/admin/llm/auto_tag_all", headers=auth_headers, timeout=30)
            assert r.status_code == 400
            assert "disabled" in r.text.lower() or "not configured" in r.text.lower()

            r = session.post(f"{API}/admin/llm/auto_describe_all", headers=auth_headers, timeout=30)
            assert r.status_code == 400
        finally:
            # Re-enable
            session.patch(f"{API}/admin/settings", json={"llm_enabled": True},
                          headers=auth_headers, timeout=30)


class TestBulkAutoTagAll:
    def test_auto_tag_all_returns_task(self, session, auth_headers, ensure_llm_enabled):
        r = session.post(f"{API}/admin/llm/auto_tag_all?force=true",
                         headers=auth_headers, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "task_id" in body and isinstance(body["task_id"], str)
        assert body["kind"] == "tags"
        assert body["status"] == "running"
        assert body["force"] is True

        # Poll status
        code, state = _wait_for_done(session, auth_headers, body["task_id"], timeout=60)
        assert code == 200
        assert state is not None
        # All required fields present
        for k in ("task_id", "kind", "force", "status", "started_at", "finished_at",
                  "total", "processed", "succeeded", "failed", "skipped_existing",
                  "current_mix", "errors", "aborted", "error"):
            assert k in state, f"Missing key: {k} in {state.keys()}"
        assert state["kind"] == "tags"
        # Since LLM is unreachable, status should be 'done' (errors caught) or 'failed' (LLMNotConfigured aborted)
        assert state["status"] in ("done", "failed")
        # And we expect the LLM unreachable to have caused failures or abort
        # Either failed > 0 OR aborted=True with an LLMNotConfigured early bail
        assert state["failed"] > 0 or state["aborted"] is True, \
            f"Expected LLM failures since LLM is unreachable. State: {state}"
        # Errors array populated
        if state["failed"] > 0:
            assert len(state["errors"]) > 0
            # Each error has required keys
            for err in state["errors"]:
                assert "mix_id" in err and "title" in err and "error" in err

    def test_auto_describe_all_returns_task(self, session, auth_headers, ensure_llm_enabled):
        r = session.post(f"{API}/admin/llm/auto_describe_all?force=true",
                         headers=auth_headers, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["kind"] == "descriptions"
        assert body["status"] == "running"
        assert body["force"] is True
        assert "task_id" in body

        code, state = _wait_for_done(session, auth_headers, body["task_id"], timeout=60)
        assert code == 200
        assert state["kind"] == "descriptions"
        assert state["status"] in ("done", "failed")

    def test_bulk_status_404_unknown(self, session, auth_headers):
        r = session.get(f"{API}/admin/llm/bulk/does-not-exist-{int(time.time())}",
                        headers=auth_headers, timeout=30)
        assert r.status_code == 404

    def test_list_bulk_tasks_shape(self, session, auth_headers):
        r = session.get(f"{API}/admin/llm/bulk", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "tasks" in data
        assert isinstance(data["tasks"], list)
        # We just kicked off at least 2 tasks above, so list should be non-empty
        assert len(data["tasks"]) >= 1


# ============== Skipping logic ==============
class TestBulkSkipping:
    @pytest.fixture
    def tagged_mix(self, session, auth_headers):
        """Create a mix, plant tags on it, yield, then cleanup."""
        payload = {
            "title": "TEST_ITER11_TAGGED",
            "artist": "TEST_DJ_ITER11",
            "genre": "Test",
            "bpm": 130,
            "description": "TEST seeded description",
        }
        r = session.post(f"{API}/admin/mixes", json=payload, headers=auth_headers, timeout=30)
        assert r.status_code == 200
        mix = r.json()
        # Plant tags + description directly via PATCH
        rp = session.patch(
            f"{API}/admin/mixes/{mix['id']}",
            json={"tags": ["test-iter11-a", "test-iter11-b"]},
            headers=auth_headers,
            timeout=30,
        )
        assert rp.status_code == 200, rp.text
        yield mix
        session.delete(f"{API}/admin/mixes/{mix['id']}", headers=auth_headers, timeout=30)

    def test_auto_tag_all_skips_existing(self, session, auth_headers, ensure_llm_enabled, tagged_mix):
        # force=false (default) — must skip the tagged mix
        r = session.post(f"{API}/admin/llm/auto_tag_all", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        task_id = r.json()["task_id"]
        code, state = _wait_for_done(session, auth_headers, task_id, timeout=60)
        assert code == 200
        # At least 1 mix should have been skipped (our tagged_mix)
        assert state["skipped_existing"] >= 1, f"Expected skipped_existing>=1, got {state}"

    def test_auto_describe_all_skips_existing(self, session, auth_headers, ensure_llm_enabled, tagged_mix):
        r = session.post(f"{API}/admin/llm/auto_describe_all", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        task_id = r.json()["task_id"]
        code, state = _wait_for_done(session, auth_headers, task_id, timeout=60)
        assert code == 200
        assert state["skipped_existing"] >= 1


# ============== Embed endpoint ==============
class TestEmbedPlayer:
    @pytest.fixture(scope="class")
    def existing_mix(self, session):
        r = session.get(f"{API}/mixes", timeout=30)
        assert r.status_code == 200
        mixes = r.json()
        assert len(mixes) > 0, "Need at least 1 mix in DB to test embed"
        return mixes[0]

    def test_embed_returns_html(self, session, existing_mix):
        r = session.get(f"{API}/embed/{existing_mix['id']}", timeout=30)
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")
        html = r.text
        # <audio controls preload="metadata" src=".../api/stream/{id}">
        assert "<audio" in html
        assert 'controls' in html
        assert 'preload="metadata"' in html
        assert f"/api/stream/{existing_mix['id']}" in html
        # Title + artist
        if existing_mix.get("title"):
            # HTML-escaped, but we can check substring of plaintext title (no `<>&`)
            assert existing_mix["title"][:20] in html or existing_mix["title"][:10] in html
        # OPEN ON MIXDECK link
        assert "OPEN ON MIXDECK" in html
        assert f"/mix/{existing_mix['id']}" in html
        # Viewport meta
        assert "viewport" in html
        assert "width=device-width" in html

    def test_embed_includes_meta_when_bpm(self, session, existing_mix):
        if not existing_mix.get("bpm"):
            pytest.skip("Mix has no BPM")
        r = session.get(f"{API}/embed/{existing_mix['id']}", timeout=30)
        assert r.status_code == 200
        assert f"{existing_mix['bpm']} BPM" in r.text

    def test_embed_404_unknown(self, session):
        r = session.get(f"{API}/embed/does-not-exist-zzz", timeout=30)
        assert r.status_code == 404


# ============== Compatible: tag-overlap scoring ==============
class TestCompatibleTagOverlap:
    @pytest.fixture
    def four_mixes(self, session, auth_headers):
        """Create:
           - SRC mix with tags [a, b, c]
           - HIGH overlap (3 shared tags) — distinct BPM
           - MED overlap (1 shared tag) — distinct BPM
           - NONE overlap (0 shared tags) but matching BPM
        """
        created = []
        defs = [
            ("TEST_ITER11_SRC", 128, ["test-i11-a", "test-i11-b", "test-i11-c"]),
            ("TEST_ITER11_HIGH", 100, ["test-i11-a", "test-i11-b", "test-i11-c"]),
            ("TEST_ITER11_MED", 105, ["test-i11-a"]),
            ("TEST_ITER11_NONE", 128, []),
        ]
        for title, bpm, tags in defs:
            payload = {
                "title": title,
                "artist": "TEST_DJ_ITER11",
                "genre": "Test",
                "bpm": bpm,
                "description": "",
            }
            r = session.post(f"{API}/admin/mixes", json=payload,
                             headers=auth_headers, timeout=30)
            assert r.status_code == 200
            m = r.json()
            if tags:
                rp = session.patch(f"{API}/admin/mixes/{m['id']}",
                                   json={"tags": tags},
                                   headers=auth_headers, timeout=30)
                assert rp.status_code == 200
            created.append((title, m, tags))
        yield created
        for _, m, _ in created:
            session.delete(f"{API}/admin/mixes/{m['id']}", headers=auth_headers, timeout=30)

    def test_compatible_sorts_by_tag_overlap(self, session, auth_headers, four_mixes):
        src = next(m for t, m, _ in four_mixes if t == "TEST_ITER11_SRC")
        high = next(m for t, m, _ in four_mixes if t == "TEST_ITER11_HIGH")
        med = next(m for t, m, _ in four_mixes if t == "TEST_ITER11_MED")

        r = session.get(f"{API}/mixes/{src['id']}/compatible?limit=20", timeout=30)
        assert r.status_code == 200, r.text
        results = r.json()
        ids = [m["id"] for m in results]
        # Both HIGH and MED must appear
        assert high["id"] in ids, f"HIGH-overlap mix missing from compatible. Got: {ids}"
        assert med["id"] in ids, f"MED-overlap mix missing from compatible. Got: {ids}"
        # HIGH should come BEFORE MED (more shared tags)
        assert ids.index(high["id"]) < ids.index(med["id"]), \
            f"HIGH ({ids.index(high['id'])}) should rank before MED ({ids.index(med['id'])})"

    def test_cache_invalidates_on_patch_tags(self, session, auth_headers, four_mixes):
        """Add a 4th shared tag to MED via PATCH and verify it now ranks higher (cache busted)."""
        src = next(m for t, m, _ in four_mixes if t == "TEST_ITER11_SRC")
        med = next(m for t, m, _ in four_mixes if t == "TEST_ITER11_MED")
        none_mix = next(m for t, m, _ in four_mixes if t == "TEST_ITER11_NONE")

        # First call to populate cache
        r = session.get(f"{API}/mixes/{src['id']}/compatible?limit=20", timeout=30)
        assert r.status_code == 200
        ids_before = [m["id"] for m in r.json()]

        # Boost NONE mix to 3 shared tags via PATCH
        rp = session.patch(
            f"{API}/admin/mixes/{none_mix['id']}",
            json={"tags": ["test-i11-a", "test-i11-b", "test-i11-c"]},
            headers=auth_headers, timeout=30,
        )
        assert rp.status_code == 200, rp.text

        # Re-fetch; cache should have been invalidated
        r2 = session.get(f"{API}/mixes/{src['id']}/compatible?limit=20", timeout=30)
        assert r2.status_code == 200
        ids_after = [m["id"] for m in r2.json()]
        # NONE-now-HIGH should now appear and outrank MED
        assert none_mix["id"] in ids_after, \
            f"After PATCH, mix should appear. ids_before={ids_before}, ids_after={ids_after}"
        assert ids_after.index(none_mix["id"]) < ids_after.index(med["id"])
