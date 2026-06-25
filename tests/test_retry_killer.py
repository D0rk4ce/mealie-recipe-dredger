"""C4: process_retry_queue must check killer.kill_now between URLs.

A SIGTERM during the retry phase should stop processing immediately, not
drain every eligible URL first.
"""
from datetime import datetime, timedelta
from unittest.mock import MagicMock
import pytest

import dredger


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(dredger, "REJECT_FILE", str(tmp_path / "rejects.json"))
    monkeypatch.setattr(dredger, "IMPORTED_FILE", str(tmp_path / "imported.json"))
    monkeypatch.setattr(dredger, "RETRY_FILE", str(tmp_path / "retry.json"))
    monkeypatch.setattr(dredger, "STATS_FILE", str(tmp_path / "stats.json"))
    monkeypatch.setattr(dredger, "SITEMAP_CACHE_FILE", str(tmp_path / "cache.json"))
    return dredger.StorageManager()


class FlipKiller:
    """kill_now becomes True after N reads."""
    def __init__(self, after):
        self._after = after
        self._reads = 0
        self._tripped = False

    @property
    def kill_now(self):
        self._reads += 1
        if self._reads > self._after:
            self._tripped = True
        return self._tripped


def _seed_eligible(storage, urls):
    long_ago = (datetime.now() - timedelta(hours=24)).isoformat()
    for u in urls:
        storage.retry_queue[u] = {
            "attempts": 0,
            "reason": "import_failed",
            "last_attempt": long_ago,
        }


def test_retry_loop_stops_when_killer_trips(storage):
    urls = [f"https://x/{i}" for i in range(5)]
    _seed_eligible(storage, urls)

    verifier = MagicMock()
    verifier.verify_recipe.return_value = (True, None, None)
    importer = MagicMock()
    importer.import_recipe.return_value = True
    rl = MagicMock()
    killer = FlipKiller(after=1)  # trip after the first URL

    dredger.process_retry_queue(storage, importer, verifier, rl, killer=killer)

    # First URL gets imported, the rest must remain in the queue
    assert len(storage.imported) == 1
    assert len(storage.retry_queue) >= 3, \
        f"Killer should have stopped the loop, retry_queue still has only {len(storage.retry_queue)} items"


def test_retry_loop_runs_all_when_killer_idle(storage):
    urls = [f"https://x/{i}" for i in range(3)]
    _seed_eligible(storage, urls)

    verifier = MagicMock()
    verifier.verify_recipe.return_value = (True, None, None)
    importer = MagicMock()
    importer.import_recipe.return_value = True
    killer = MagicMock()
    killer.kill_now = False

    dredger.process_retry_queue(storage, importer, verifier, MagicMock(), killer=killer)

    assert len(storage.imported) == 3
    assert len(storage.retry_queue) == 0


def test_retry_loop_works_without_killer_for_back_compat(storage):
    """Killer is optional; absent killer must not break."""
    urls = ["https://x/only"]
    _seed_eligible(storage, urls)

    verifier = MagicMock()
    verifier.verify_recipe.return_value = (True, None, None)
    importer = MagicMock()
    importer.import_recipe.return_value = True

    dredger.process_retry_queue(storage, importer, verifier, MagicMock())
    assert "https://x/only" in storage.imported
