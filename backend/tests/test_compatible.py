"""Tests for iteration 4: GET /api/mixes/{id}/compatible endpoint.

Covers:
- 200 + List[Mix] response for existing mix
- 404 for non-existent mix
- Source mix excluded from results
- Camelot adjacency (same, +/-1 with wrap, relative major/minor)
- BPM proximity (+/-4) bonus
- Genre bonus
- ?limit= query param
- No MongoDB _id leak
- Ordering by score (best first)
- Edge: source with no bpm/camelot
- Regression: GET /api/mixes/{id} still works
"""
import os
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
ADMIN_PASSWORD = "mixdeck2026"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


@pytest.fixture(scope="module")
def session():
    return requests.Session()


@pytest.fixture(scope="module")
def auth_headers(session):
    r = session.post(f"{API}/auth/login", json={"password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def mongo_db():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


def _create_mix(session, auth_headers, mongo_db, title, bpm, camelot, genre):
    """Create a mix via API then patch camelot directly in mongo (not exposed in API model)."""
    r = session.post(
        f"{API}/admin/mixes",
        json={"title": title, "genre": genre, "bpm": bpm},
        headers=auth_headers,
        timeout=30,
    )
    assert r.status_code == 200, r.text
    mix = r.json()
    # camelot is not part of MixCreate/MixUpdate -> set directly in Mongo
    mongo_db.mixes.update_one({"id": mix["id"]}, {"$set": {"camelot": camelot}})
    mix["camelot"] = camelot
    return mix


@pytest.fixture(scope="module")
def compat_set(session, auth_headers, mongo_db):
    """Create A/B/C/D mixes per test plan."""
    created = {
        "A": _create_mix(session, auth_headers, mongo_db, "TEST_COMPAT_A", 138, "9A", "TEST_CompatHouseA"),
        "B": _create_mix(session, auth_headers, mongo_db, "TEST_COMPAT_B", 140, "10A", "TEST_CompatHouseA"),
        "C": _create_mix(session, auth_headers, mongo_db, "TEST_COMPAT_C", 120, "8A", "TEST_CompatHouseA"),
        "D": _create_mix(session, auth_headers, mongo_db, "TEST_COMPAT_D", 90, "5B", "TEST_CompatOtherD"),
    }
    yield created
    for m in created.values():
        try:
            session.delete(f"{API}/admin/mixes/{m['id']}", headers=auth_headers, timeout=30)
        except Exception:
            pass


# ========== Compatible endpoint ==========
class TestCompatibleBasics:
    def test_returns_200_and_list(self, session, compat_set):
        r = session.get(f"{API}/mixes/{compat_set['A']['id']}/compatible", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_404_for_missing_mix(self, session):
        r = session.get(f"{API}/mixes/does-not-exist-xyz/compatible", timeout=30)
        assert r.status_code == 404

    def test_source_excluded(self, session, compat_set):
        src_id = compat_set["A"]["id"]
        r = session.get(f"{API}/mixes/{src_id}/compatible", timeout=30)
        assert r.status_code == 200
        ids = [m["id"] for m in r.json()]
        assert src_id not in ids

    def test_no_mongo_id_leak(self, session, compat_set):
        r = session.get(f"{API}/mixes/{compat_set['A']['id']}/compatible", timeout=30)
        assert r.status_code == 200
        for m in r.json():
            assert "_id" not in m
            assert "id" in m


class TestCompatibleScoring:
    def test_B_and_C_match_D_does_not(self, session, compat_set):
        """Source A(138, 9A). B(140, 10A adjacent) + C(120, 8A adjacent) should match.
        D(90, 5B, different genre) should NOT match."""
        r = session.get(f"{API}/mixes/{compat_set['A']['id']}/compatible?limit=50", timeout=30)
        assert r.status_code == 200
        ids = [m["id"] for m in r.json()]
        assert compat_set["B"]["id"] in ids
        assert compat_set["C"]["id"] in ids
        assert compat_set["D"]["id"] not in ids

    def test_ordering_best_first(self, session, compat_set):
        """B(10A, bpm diff 2) should outrank C(8A, bpm diff 18).
        Both adjacent in Camelot (+3), both same genre (+1). B gets bpm bonus of 2 (4-2), C gets 0.
        So B > C."""
        r = session.get(f"{API}/mixes/{compat_set['A']['id']}/compatible?limit=50", timeout=30)
        assert r.status_code == 200
        ids = [m["id"] for m in r.json()]
        assert ids.index(compat_set["B"]["id"]) < ids.index(compat_set["C"]["id"])

    def test_limit_param(self, session, compat_set):
        r = session.get(f"{API}/mixes/{compat_set['A']['id']}/compatible?limit=1", timeout=30)
        assert r.status_code == 200
        results = r.json()
        assert len(results) == 1
        # Source not included; no _id leak
        assert results[0]["id"] != compat_set["A"]["id"]
        assert "_id" not in results[0]

    def test_limit_2(self, session, compat_set):
        r = session.get(f"{API}/mixes/{compat_set['A']['id']}/compatible?limit=2", timeout=30)
        assert r.status_code == 200
        assert len(r.json()) <= 2

    def test_default_limit_is_8(self, session, compat_set):
        # without limit param returned list bounded by default 8
        r = session.get(f"{API}/mixes/{compat_set['A']['id']}/compatible", timeout=30)
        assert r.status_code == 200
        assert len(r.json()) <= 8


class TestCompatibleEdge:
    def test_source_without_bpm_or_camelot(self, session, auth_headers, mongo_db, compat_set):
        """Mix with no bpm/camelot: only genre-matching mixes should be returned (or empty)."""
        r = session.post(
            f"{API}/admin/mixes",
            json={"title": "TEST_COMPAT_NOMETA", "genre": "TEST_CompatHouseA"},
            headers=auth_headers,
            timeout=30,
        )
        assert r.status_code == 200
        nm = r.json()
        try:
            resp = session.get(f"{API}/mixes/{nm['id']}/compatible", timeout=30)
            assert resp.status_code == 200
            results = resp.json()
            # All returned must share the same genre (score>0 only via +1 genre)
            for m in results:
                assert m.get("genre") == "TEST_CompatHouseA"
            # The 3 sibling mixes in same genre (A/B/C) should all be present
            ids = {m["id"] for m in results}
            assert compat_set["A"]["id"] in ids
            assert compat_set["B"]["id"] in ids
            assert compat_set["C"]["id"] in ids
            assert compat_set["D"]["id"] not in ids
        finally:
            session.delete(f"{API}/admin/mixes/{nm['id']}", headers=auth_headers, timeout=30)

    def test_wrap_around_camelot_12_to_1(self, session, auth_headers, mongo_db):
        """Edge case: 12A should be adjacent to 1A (wrap)."""
        r = session.post(
            f"{API}/admin/mixes",
            json={"title": "TEST_WRAP_12A", "bpm": 128},
            headers=auth_headers,
            timeout=30,
        )
        src = r.json()
        mongo_db.mixes.update_one({"id": src["id"]}, {"$set": {"camelot": "12A"}})
        r2 = session.post(
            f"{API}/admin/mixes",
            json={"title": "TEST_WRAP_1A", "bpm": 128},
            headers=auth_headers,
            timeout=30,
        )
        adj = r2.json()
        mongo_db.mixes.update_one({"id": adj["id"]}, {"$set": {"camelot": "1A"}})
        try:
            resp = session.get(f"{API}/mixes/{src['id']}/compatible?limit=50", timeout=30)
            assert resp.status_code == 200
            ids = [m["id"] for m in resp.json()]
            assert adj["id"] in ids, "1A should be adjacent to 12A (wrap)"
        finally:
            session.delete(f"{API}/admin/mixes/{src['id']}", headers=auth_headers, timeout=30)
            session.delete(f"{API}/admin/mixes/{adj['id']}", headers=auth_headers, timeout=30)

    def test_wrap_around_camelot_1_to_12(self, session, auth_headers, mongo_db):
        """Edge case: 1A should be adjacent to 12A (wrap the other way)."""
        r = session.post(
            f"{API}/admin/mixes",
            json={"title": "TEST_WRAP_1A_SRC", "bpm": 128},
            headers=auth_headers,
            timeout=30,
        )
        src = r.json()
        mongo_db.mixes.update_one({"id": src["id"]}, {"$set": {"camelot": "1A"}})
        r2 = session.post(
            f"{API}/admin/mixes",
            json={"title": "TEST_WRAP_12A_ADJ", "bpm": 128},
            headers=auth_headers,
            timeout=30,
        )
        adj = r2.json()
        mongo_db.mixes.update_one({"id": adj["id"]}, {"$set": {"camelot": "12A"}})
        try:
            resp = session.get(f"{API}/mixes/{src['id']}/compatible?limit=50", timeout=30)
            assert resp.status_code == 200
            ids = [m["id"] for m in resp.json()]
            assert adj["id"] in ids, "12A should be adjacent to 1A (wrap the other way)"
        finally:
            session.delete(f"{API}/admin/mixes/{src['id']}", headers=auth_headers, timeout=30)
            session.delete(f"{API}/admin/mixes/{adj['id']}", headers=auth_headers, timeout=30)

    def test_relative_major_minor(self, session, auth_headers, mongo_db):
        """8A (minor) and 8B (relative major) should match each other."""
        r = session.post(
            f"{API}/admin/mixes",
            json={"title": "TEST_REL_8A", "bpm": 128},
            headers=auth_headers,
            timeout=30,
        )
        src = r.json()
        mongo_db.mixes.update_one({"id": src["id"]}, {"$set": {"camelot": "8A"}})
        r2 = session.post(
            f"{API}/admin/mixes",
            json={"title": "TEST_REL_8B", "bpm": 128},
            headers=auth_headers,
            timeout=30,
        )
        rel = r2.json()
        mongo_db.mixes.update_one({"id": rel["id"]}, {"$set": {"camelot": "8B"}})
        try:
            resp = session.get(f"{API}/mixes/{src['id']}/compatible?limit=50", timeout=30)
            assert resp.status_code == 200
            ids = [m["id"] for m in resp.json()]
            assert rel["id"] in ids, "8B should be relative major of 8A"
        finally:
            session.delete(f"{API}/admin/mixes/{src['id']}", headers=auth_headers, timeout=30)
            session.delete(f"{API}/admin/mixes/{rel['id']}", headers=auth_headers, timeout=30)


# ========== Regression for deep-seek frontend dep ==========
class TestGetMixRegression:
    def test_get_mix_still_works(self, session, compat_set):
        """Deep-seek ?t=MM:SS frontend feature depends on GET /api/mixes/{id} returning full Mix."""
        r = session.get(f"{API}/mixes/{compat_set['A']['id']}", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == compat_set["A"]["id"]
        assert data["title"] == "TEST_COMPAT_A"
        assert data["bpm"] == 138
        assert "_id" not in data
        # duration field must exist (used by player to scrub)
        assert "duration" in data

    def test_get_mix_404(self, session):
        r = session.get(f"{API}/mixes/does-not-exist-xyz", timeout=30)
        assert r.status_code == 404
