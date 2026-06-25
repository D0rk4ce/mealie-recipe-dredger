"""Review suggestions:

- #6 ntfy.sh webhook: ntfy expects raw body, not JSON. Branch on host.
- #10 token-based junk match: "shop" must NOT match "shopska-salad".
- #13 JSON-LD parsing: only count true Recipe @type, not substring inside script text.
- #20 endpoint fallback also on auth-failure when cached endpoint was wrong.
"""
import json
from unittest.mock import MagicMock, patch
import pytest

import dredger
from maintenance import master_cleaner


# --- #10 token-based filter ---

def test_is_paranoid_skip_does_not_false_positive_on_shop_substring():
    # "shop" must not flag "shopska-salad"
    verifier = dredger.RecipeVerifier(MagicMock())
    assert verifier.is_paranoid_skip("https://example.com/recipes/shopska-salad") is None


def test_is_paranoid_skip_still_flags_actual_shop_token():
    verifier = dredger.RecipeVerifier(MagicMock())
    res = verifier.is_paranoid_skip("https://example.com/shop")
    assert res is not None and "shop" in res.lower()


def test_is_paranoid_skip_still_flags_hyphenated_token():
    verifier = dredger.RecipeVerifier(MagicMock())
    res = verifier.is_paranoid_skip("https://example.com/blog/our-product-roundup")
    assert res is not None


def test_master_cleaner_junk_filter_does_not_false_positive_on_preview():
    # "review" substring of "preview" — current bug: returns True
    assert master_cleaner.is_junk_content(
        name="Preview of summer recipes",
        url="https://example.com/preview-summer",
    ) is False


# --- #13 JSON-LD real parsing ---

def test_recipe_detection_ignores_recipe_string_in_unrelated_script():
    # An ordinary article page that happens to contain `"@type":"Recipe"` in
    # an unrelated inline script (e.g. analytics, ad config). The page itself
    # is NOT a recipe. Must not be flagged.
    body = (
        '<html><body>'
        '<script>var trackingPayload = {"events":[{"@type":"Recipe","name":"x"}]};</script>'
        '<article>An interesting blog post about cooking</article>'
        '</body></html>'
    ).encode("utf-8")
    session = MagicMock()
    session.get.return_value = MagicMock(status_code=200, text=body.decode("utf-8"), content=body)
    v = dredger.RecipeVerifier(session)
    is_recipe, _, _ = v.verify_recipe("https://example.com/article")
    assert is_recipe is False, "Random script with Recipe substring should not be treated as a recipe"


def test_recipe_detection_finds_real_jsonld_recipe():
    body = (
        '<html><body>'
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"Recipe","name":"Real recipe"}'
        '</script>'
        '<div>Recipe content here</div>'
        '</body></html>'
    ).encode("utf-8")
    session = MagicMock()
    session.get.return_value = MagicMock(status_code=200, text=body.decode("utf-8"), content=body)
    v = dredger.RecipeVerifier(session)
    is_recipe, _, _ = v.verify_recipe("https://example.com/real")
    assert is_recipe is True


def test_recipe_detection_handles_jsonld_graph_format():
    # Schema.org @graph variant — common on WP sites
    body = (
        '<html><body>'
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","@graph":['
        '{"@type":"WebPage"},{"@type":"Recipe","name":"X"}]}'
        '</script>'
        '</body></html>'
    ).encode("utf-8")
    session = MagicMock()
    session.get.return_value = MagicMock(status_code=200, text=body.decode("utf-8"), content=body)
    v = dredger.RecipeVerifier(session)
    is_recipe, _, _ = v.verify_recipe("https://example.com/graph")
    assert is_recipe is True


# --- #6 ntfy webhook ---

def test_ntfy_webhook_uses_raw_body(monkeypatch):
    monkeypatch.setattr(dredger, "NOTIFICATION_WEBHOOK_URL", "https://ntfy.sh/my-topic")
    storage = MagicMock(imported=set(), rejects=set(), retry_queue={}, sitemap_cache={})
    with patch("dredger.requests.post") as p:
        dredger.send_notification(storage)
    p.assert_called_once()
    args, kwargs = p.call_args
    # ntfy must NOT receive a JSON content payload — it expects data=text
    assert "json" not in kwargs or kwargs.get("json") is None, \
        "ntfy.sh expects raw body, not JSON payload"
    assert "data" in kwargs, "ntfy.sh path must use data= for the raw body"


def test_discord_webhook_uses_content_json(monkeypatch):
    monkeypatch.setattr(dredger, "NOTIFICATION_WEBHOOK_URL", "https://discord.com/api/webhooks/123/abc")
    storage = MagicMock(imported=set(), rejects=set(), retry_queue={}, sitemap_cache={})
    with patch("dredger.requests.post") as p:
        dredger.send_notification(storage)
    args, kwargs = p.call_args
    assert kwargs.get("json", {}).get("content"), "Discord uses json={'content': ...}"


def test_slack_webhook_uses_text_json(monkeypatch):
    monkeypatch.setattr(dredger, "NOTIFICATION_WEBHOOK_URL", "https://hooks.slack.com/services/T/X/Y")
    storage = MagicMock(imported=set(), rejects=set(), retry_queue={}, sitemap_cache={})
    with patch("dredger.requests.post") as p:
        dredger.send_notification(storage)
    args, kwargs = p.call_args
    assert kwargs.get("json", {}).get("text"), "Slack uses json={'text': ...}"


# --- #20 endpoint fallback on auth failure ---

def test_mealie_endpoint_fallback_on_401(monkeypatch):
    monkeypatch.setattr(dredger, "MEALIE_URL", "http://mealie.test")
    monkeypatch.setattr(dredger, "MEALIE_API_TOKEN", "tok")
    session = MagicMock()
    # First endpoint returns 404 (not a valid path on this Mealie),
    # but the simulated server normally returns 401 if you guess wrong.
    # We pin: 401 on the first attempt should NOT cache the wrong endpoint
    # and should try the next one.
    responses = [MagicMock(status_code=401), MagicMock(status_code=201)]
    session.post.side_effect = responses
    rl = MagicMock()
    storage = MagicMock()
    importer = dredger.ImportManager(session, storage, rl, dry_run=False)
    ok, _ = importer.import_to_mealie("https://x/r")
    assert ok is True, "Auth failure on first endpoint should let the second be tried"
    assert session.post.call_count == 2
