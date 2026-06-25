"""C1: failed imports must be enqueued into the retry queue.

The original main loop discarded failures: they were only counted as errors and
never given a second chance. These tests pin the new behaviour:
process_candidate() must add to retry_queue on import failure and *not* mark
the URL as rejected.
"""
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


def _make_verifier(is_recipe=True, error=None):
    v = MagicMock()
    v.verify_recipe.return_value = (is_recipe, None, error)
    return v


def _make_importer(success):
    i = MagicMock()
    i.import_recipe.return_value = success
    return i


def test_import_failure_enqueues_url_into_retry_queue(storage):
    url = "https://example.com/recipe-1"
    site_stats = {"imported": 0, "rejected": 0, "errors": 0}

    dredger.process_candidate(
        url,
        storage,
        importer=_make_importer(success=False),
        verifier=_make_verifier(),
        rate_limiter=MagicMock(),
        site_stats=site_stats,
    )

    assert url in storage.retry_queue
    assert storage.retry_queue[url]["attempts"] == 0
    assert url not in storage.rejects
    assert url not in storage.imported
    assert site_stats["errors"] == 1


def test_import_success_marks_imported_not_retry(storage):
    url = "https://example.com/recipe-2"
    site_stats = {"imported": 0, "rejected": 0, "errors": 0}

    dredger.process_candidate(
        url,
        storage,
        importer=_make_importer(success=True),
        verifier=_make_verifier(),
        rate_limiter=MagicMock(),
        site_stats=site_stats,
    )

    assert url in storage.imported
    assert url not in storage.retry_queue
    assert site_stats["imported"] == 1


def test_non_recipe_is_rejected_not_retried(storage):
    url = "https://example.com/not-a-recipe"
    site_stats = {"imported": 0, "rejected": 0, "errors": 0}

    dredger.process_candidate(
        url,
        storage,
        importer=_make_importer(success=True),
        verifier=_make_verifier(is_recipe=False, error="No recipe detected"),
        rate_limiter=MagicMock(),
        site_stats=site_stats,
    )

    assert url in storage.rejects
    assert url not in storage.retry_queue
    assert site_stats["rejected"] == 1
