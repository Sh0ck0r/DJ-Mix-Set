"""Shared helper for the new background scan polling contract.

POST /api/admin/scan now returns {task_id, status:'running'} immediately.
Use scan_and_wait() to submit + poll until 'done' or 'failed' and get the
final state (which carries added/skipped/failed/scanned counters and arrays).
"""
import time

POLL_INTERVAL = 0.4
DEFAULT_TIMEOUT = 90.0


def scan_and_wait(session, api_base, headers, body, timeout=DEFAULT_TIMEOUT):
    """Submit a scan and poll until terminal. Returns the final state dict.

    Adds a 'scanned' alias equal to 'total' so legacy tests that read
    body['scanned'] keep working.
    """
    r = session.post(f"{api_base}/admin/scan", json=body, headers=headers, timeout=15)
    if r.status_code != 200:
        return r  # let caller assert on failure
    task_id = r.json()["task_id"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = session.get(f"{api_base}/admin/scan/{task_id}", headers=headers, timeout=15)
        if s.status_code != 200:
            raise AssertionError(f"poll failed: {s.status_code} {s.text}")
        state = s.json()
        if state["status"] in ("done", "failed"):
            # Backwards-compat alias
            state.setdefault("scanned", state.get("total", 0))
            # Wrap so callers can do `r.status_code == 200` AND `r.json() == state`
            return _Wrapped(state)
        time.sleep(POLL_INTERVAL)
    raise AssertionError(f"scan {task_id} did not finish in {timeout}s")


class _Wrapped:
    """Mimics requests.Response just enough for legacy tests."""

    def __init__(self, state):
        self._state = state
        self.status_code = 200

    def json(self):
        return self._state

    @property
    def text(self):
        import json as _json

        return _json.dumps(self._state)
