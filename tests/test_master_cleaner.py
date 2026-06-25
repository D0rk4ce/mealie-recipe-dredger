"""C2: DELETE handlers must treat any 2xx as success.

The original code only accepted HTTP 200, causing 3x retries against APIs that
return 204 No Content (REST-conventional for DELETE). These tests pin the new
behaviour: a 204 response leaves max_retries unused.
"""
from unittest.mock import MagicMock, patch
import importlib


def _import_cleaner(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("MEALIE_API_TOKEN", "test-token")
    monkeypatch.setenv("TANDOOR_API_KEY", "test-key")
    # importlib.reload guarantees the module body re-runs with our env active,
    # even if another test already imported it under different env.
    from maintenance import master_cleaner
    return importlib.reload(master_cleaner)


def test_mealie_delete_accepts_204_no_retries(tmp_path, monkeypatch):
    cleaner = _import_cleaner(tmp_path, monkeypatch)
    response = MagicMock(status_code=204)
    with patch("maintenance.master_cleaner.requests.delete", return_value=response) as mock_del:
        cleaner.delete_mealie_recipe("slug-1", "Test", "JUNK", url="https://x/r")
    assert mock_del.call_count == 1, "204 must be treated as success (no retry storm)"


def test_mealie_delete_retries_on_500_up_to_three(tmp_path, monkeypatch):
    cleaner = _import_cleaner(tmp_path, monkeypatch)
    response = MagicMock(status_code=500)
    with patch("maintenance.master_cleaner.requests.delete", return_value=response) as mock_del, \
         patch("maintenance.master_cleaner.time.sleep"):
        cleaner.delete_mealie_recipe("slug-2", "Test", "JUNK", url="https://x/r")
    assert mock_del.call_count == 3, "500 must trigger up to 3 attempts"


def test_mealie_delete_accepts_200(tmp_path, monkeypatch):
    cleaner = _import_cleaner(tmp_path, monkeypatch)
    response = MagicMock(status_code=200)
    with patch("maintenance.master_cleaner.requests.delete", return_value=response) as mock_del:
        cleaner.delete_mealie_recipe("slug-3", "Test", "JUNK")
    assert mock_del.call_count == 1
