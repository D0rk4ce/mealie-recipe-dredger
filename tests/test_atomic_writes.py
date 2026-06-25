"""C3: state writes must be crash-safe.

The original code did open(filename, 'w') which truncates first; a crash
mid-serialize leaves the file empty or partial and the next process refuses
to load it. These tests pin a tmp+rename pattern.
"""
import json
import os
from unittest.mock import patch

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


def test_save_set_preserves_prior_content_on_serialize_crash(tmp_path, storage):
    storage.rejects.add("https://good.example/old")
    storage._save_json_set(dredger.REJECT_FILE, storage.rejects)

    storage.rejects.add("https://good.example/new")

    def boom(*_a, **_kw):
        raise IOError("simulated crash")

    with patch("dredger.json.dump", side_effect=boom):
        with pytest.raises(IOError):
            storage._save_json_set(dredger.REJECT_FILE, storage.rejects)

    with open(dredger.REJECT_FILE) as f:
        data = set(json.load(f))
    assert data == {"https://good.example/old"}, \
        "Original file must be intact after a crashed write"


def test_save_dict_preserves_prior_content_on_serialize_crash(tmp_path, storage):
    storage.retry_queue["https://x/1"] = {"attempts": 0}
    storage._save_json_dict(dredger.RETRY_FILE, storage.retry_queue)

    storage.retry_queue["https://x/2"] = {"attempts": 0}
    with patch("dredger.json.dump", side_effect=IOError("simulated")):
        with pytest.raises(IOError):
            storage._save_json_dict(dredger.RETRY_FILE, storage.retry_queue)

    with open(dredger.RETRY_FILE) as f:
        data = json.load(f)
    assert data == {"https://x/1": {"attempts": 0}}


def test_no_stale_tmp_file_left_behind_on_success(tmp_path, storage):
    storage.rejects.add("https://x/1")
    storage._save_json_set(dredger.REJECT_FILE, storage.rejects)
    tmp_candidates = [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert tmp_candidates == [], "Successful write must not leave .tmp file"
