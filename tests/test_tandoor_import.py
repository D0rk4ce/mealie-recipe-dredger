"""Issue #6: Tandoor v2 import endpoint.

The old `/api/recipe/import-url/` endpoint no longer exists in Tandoor v2 — POSTs
return 405. The reporter (wkleinhenz, Tandoor 2.6.4) guessed `api/recipe-import/`,
but that ViewSet is the legacy admin-only RecipeImport staging model, not a URL
importer.

The real v2 URL importer is `POST /api/recipe-from-source/` (RecipeUrlImportView),
which **scrapes and returns parsed JSON but does not persist** for a normal blog
URL. Persisting requires a second `POST /api/recipe/` with the scraped recipe.

These tests pin the two-step flow.
"""
from unittest.mock import MagicMock
import pytest

import dredger


def _resp(status_code, json_body=None):
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = json_body if json_body is not None else {}
    return r


@pytest.fixture
def importer(monkeypatch):
    monkeypatch.setattr(dredger, "TANDOOR_URL", "https://tandoor.test")
    monkeypatch.setattr(dredger, "TANDOOR_API_KEY", "tok-rw")
    session = MagicMock()
    rl = MagicMock()
    storage = MagicMock()
    return dredger.ImportManager(session, storage, rl, dry_run=False), session


SCRAPE_OK = {
    "error": False,
    "recipe": {
        "name": "Reese Peanut Butter Chip Cookies",
        "description": "Soft cookies",
        "source_url": "https://livforcake.com/reese-peanut-butter-chip-cookies/",
        "servings": 24,
        "working_time": 20,
        "waiting_time": 10,
        "steps": [
            {
                "instruction": "Mix it all",
                "show_ingredients_table": True,
                "ingredients": [
                    {"amount": 2.0, "food": {"name": "flour"}, "unit": {"name": "cup"},
                     "note": "", "original_text": "2 cups flour"}
                ],
            }
        ],
        "keywords": [
            {"id": None, "label": "dessert", "name": "dessert", "import_keyword": True}
        ],
    },
    "images": ["https://livforcake.com/img.jpg"],
    "duplicates": [],
}


def test_import_calls_recipe_from_source_then_create(importer):
    mgr, session = importer
    session.post.side_effect = [
        _resp(200, SCRAPE_OK),          # scrape
        _resp(201, {"id": 42}),          # create
    ]

    ok, err = mgr.import_to_tandoor("https://livforcake.com/reese-peanut-butter-chip-cookies/")

    assert ok is True, f"expected success, got error={err}"
    assert session.post.call_count == 2
    first_url = session.post.call_args_list[0].args[0] if session.post.call_args_list[0].args \
        else session.post.call_args_list[0].kwargs["url"]
    second_url = session.post.call_args_list[1].args[0] if session.post.call_args_list[1].args \
        else session.post.call_args_list[1].kwargs["url"]
    assert first_url == "https://tandoor.test/api/recipe-from-source/"
    assert second_url == "https://tandoor.test/api/recipe/"


def test_import_short_circuits_when_scrape_already_created(importer):
    # YouTube / Tandoor-share URLs are persisted by the scrape view itself,
    # which returns recipe_id. No second POST should happen.
    mgr, session = importer
    session.post.side_effect = [_resp(200, {"error": False, "recipe_id": 99})]

    ok, err = mgr.import_to_tandoor("https://youtu.be/abc")

    assert ok is True
    assert session.post.call_count == 1


def test_import_treats_existing_duplicate_as_success(importer):
    mgr, session = importer
    body = {"error": False, "recipe": SCRAPE_OK["recipe"],
            "duplicates": [{"id": 7, "name": "Reese Cookies"}]}
    session.post.side_effect = [_resp(200, body)]

    ok, err = mgr.import_to_tandoor("https://livforcake.com/x/")

    assert ok is True, f"duplicate should count as success, got error={err}"
    assert session.post.call_count == 1, "no create POST when it's already in the library"


def test_import_reports_405_on_scrape_without_creating(importer):
    # The exact symptom from issue #6 — but now against the correct endpoint.
    mgr, session = importer
    session.post.side_effect = [_resp(405, {})]

    ok, err = mgr.import_to_tandoor("https://livforcake.com/x/")

    assert ok is False
    assert "405" in (err or "")
    assert session.post.call_count == 1


def test_import_surfaces_scrape_error_payload(importer):
    mgr, session = importer
    session.post.side_effect = [_resp(200, {"error": True, "msg": "No usable data could be found."})]

    ok, err = mgr.import_to_tandoor("https://livforcake.com/not-a-recipe/")

    assert ok is False
    assert "No usable data" in (err or "")
    assert session.post.call_count == 1


def test_import_reports_create_failure(importer):
    mgr, session = importer
    session.post.side_effect = [_resp(200, SCRAPE_OK), _resp(400, {})]

    ok, err = mgr.import_to_tandoor("https://livforcake.com/x/")

    assert ok is False
    assert "400" in (err or "")
    assert session.post.call_count == 2


def test_dry_run_makes_no_network_calls(monkeypatch):
    monkeypatch.setattr(dredger, "TANDOOR_URL", "https://tandoor.test")
    monkeypatch.setattr(dredger, "TANDOOR_API_KEY", "tok")
    session = MagicMock()
    mgr = dredger.ImportManager(session, MagicMock(), MagicMock(), dry_run=True)
    ok, err = mgr.import_to_tandoor("https://x/r")
    assert ok is True
    session.post.assert_not_called()


# --- payload builder ---

def test_build_payload_strips_null_keyword_id_and_sets_internal():
    payload = dredger._build_tandoor_create_payload(
        SCRAPE_OK["recipe"], fallback_url="https://livforcake.com/x/"
    )
    assert payload["internal"] is True
    assert payload["name"] == "Reese Peanut Butter Chip Cookies"
    # keyword id=None must not be sent (breaks writable-nested PK lookup)
    for kw in payload["keywords"]:
        assert "id" not in kw or kw["id"] is not None
        assert kw["name"] == "dessert"
    # steps passed through with ingredients intact
    assert payload["steps"][0]["ingredients"][0]["food"]["name"] == "flour"


def test_build_payload_falls_back_to_url_when_source_missing():
    recipe = {"name": "X", "steps": []}
    payload = dredger._build_tandoor_create_payload(recipe, fallback_url="https://blog/x/")
    assert payload["source_url"] == "https://blog/x/"


def test_build_payload_always_includes_steps_list():
    # /api/recipe/ requires steps; ensure we never omit it
    recipe = {"name": "X"}
    payload = dredger._build_tandoor_create_payload(recipe, fallback_url="https://blog/x/")
    assert isinstance(payload["steps"], list)
