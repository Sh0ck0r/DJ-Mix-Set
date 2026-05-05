"""Tests for background scan + analysis_overview (iteration 7)."""
import os
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://dj-cue-hub.preview.emergentagent.com").rstrip("/")
ADMIN_PASSWORD = "mixdeck2026"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth(token):
    return {"Authorization": f"Bearer {token}"}


# Auth: all 3 endpoints reject without/bad token
def test_scan_post_no_auth():
    r = requests.post(f"{BASE_URL}/api/admin/scan", json={"path": "/tmp"}, timeout=15)
    assert r.status_code in (401, 403)


def test_scan_status_no_auth():
    r = requests.get(f"{BASE_URL}/api/admin/scan/some-id", timeout=15)
    assert r.status_code in (401, 403)


def test_analysis_overview_no_auth():
    r = requests.get(f"{BASE_URL}/api/admin/analysis_overview", timeout=15)
    assert r.status_code in (401, 403)


def test_scan_post_bad_token():
    r = requests.post(
        f"{BASE_URL}/api/admin/scan",
        json={"path": "/tmp"},
        headers={"Authorization": "Bearer not-a-real-token"},
        timeout=15,
    )
    assert r.status_code == 401


# POST /api/admin/scan invalid path -> 400 sync
def test_scan_invalid_path_returns_400(auth):
    r = requests.post(
        f"{BASE_URL}/api/admin/scan",
        json={"path": "/this/does/not/exist/xyz123", "analyze": False},
        headers=auth,
        timeout=15,
    )
    assert r.status_code == 400
    assert "detail" in r.json()


# Unknown task id -> 404
def test_scan_status_unknown_id(auth):
    r = requests.get(f"{BASE_URL}/api/admin/scan/00000000-aaaa-bbbb-cccc-000000000000", headers=auth, timeout=15)
    assert r.status_code == 404


# analysis_overview shape
def test_analysis_overview_shape(auth):
    r = requests.get(f"{BASE_URL}/api/admin/analysis_overview", headers=auth, timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert set(["counts", "total", "active_workers"]).issubset(data.keys())
    counts = data["counts"]
    for k in ("none", "pending", "running", "done", "failed"):
        assert k in counts
        assert isinstance(counts[k], int)
    assert sum(counts.values()) == data["total"]
    assert isinstance(data["active_workers"], int)


# Full scan flow on /tmp - returns task_id immediately, polling, idempotency, cache invalidation, cleanup
def test_scan_full_flow_on_tmp(auth):
    # Pre-state mix count
    pre = requests.get(f"{BASE_URL}/api/mixes", timeout=15)
    assert pre.status_code == 200
    pre_ids = {m["id"] for m in pre.json()}
    pre_count = len(pre_ids)

    # POST scan - should return immediately
    t0 = time.time()
    r = requests.post(
        f"{BASE_URL}/api/admin/scan",
        json={"path": "/tmp", "recursive": True, "analyze": False, "default_genre": "TEST_BG"},
        headers=auth,
        timeout=15,
    )
    elapsed = time.time() - t0
    assert r.status_code == 200, r.text
    body = r.json()
    assert "task_id" in body
    assert body["status"] == "running"
    task_id = body["task_id"]
    # Should be near-instant (allow up to 5s for network)
    assert elapsed < 5.0, f"POST scan took {elapsed}s - should be async"

    # Poll until done
    final = None
    saw_running = False
    deadline = time.time() + 60
    while time.time() < deadline:
        s = requests.get(f"{BASE_URL}/api/admin/scan/{task_id}", headers=auth, timeout=15)
        assert s.status_code == 200
        state = s.json()
        # Required keys
        for k in ("processed", "total", "added_count", "skipped_count", "failed_count", "added", "skipped", "failed", "status"):
            assert k in state
        if state["status"] == "running":
            saw_running = True
        if state["status"] in ("done", "failed"):
            final = state
            break
        time.sleep(0.5)
    assert final is not None, "Scan never finished within 60s"
    assert final["status"] == "done", f"Scan failed: {final}"
    assert isinstance(final["added"], list)
    assert isinstance(final["skipped"], list)
    assert isinstance(final["failed"], list)
    assert final["added_count"] == len(final["added"])
    assert final["skipped_count"] == len(final["skipped"])
    assert final["failed_count"] == len(final["failed"])

    # Cache invalidation: GET /api/mixes should reflect new count immediately if anything was added
    post = requests.get(f"{BASE_URL}/api/mixes", timeout=15)
    assert post.status_code == 200
    post_ids = {m["id"] for m in post.json()}
    new_ids = post_ids - pre_ids
    if final["added_count"] > 0:
        assert len(new_ids) == final["added_count"], (
            f"Cache stale: added_count={final['added_count']} but mixes diff={len(new_ids)}"
        )

    # Idempotency: re-run scan, all should be skipped (already_ingested)
    r2 = requests.post(
        f"{BASE_URL}/api/admin/scan",
        json={"path": "/tmp", "recursive": True, "analyze": False},
        headers=auth,
        timeout=15,
    )
    assert r2.status_code == 200
    tid2 = r2.json()["task_id"]
    final2 = None
    deadline = time.time() + 60
    while time.time() < deadline:
        s = requests.get(f"{BASE_URL}/api/admin/scan/{tid2}", headers=auth, timeout=15)
        st = s.json()
        if st["status"] in ("done", "failed"):
            final2 = st
            break
        time.sleep(0.4)
    assert final2 is not None
    assert final2["status"] == "done"
    # Every previously-added mix should now be in skipped with reason already_ingested
    if final["added_count"] > 0:
        assert final2["added_count"] == 0, "Idempotency violation - duplicates added"
        reasons = {s.get("reason") for s in final2["skipped"]}
        assert "already_ingested" in reasons

    # Cleanup any TEST_BG mixes we created
    for mix_id in new_ids:
        requests.delete(f"{BASE_URL}/api/admin/mixes/{mix_id}", headers=auth, timeout=15)
