"""C5 + user feature request.

- SITES env: accept either a comma-separated URL list OR a path to a JSON file
  (.env.example documents the path form, the original code only handled the
  list form, the README ships both — pin both behaviours).
- LANGUAGE_FILTER: accept multiple ISO codes ("en,pt" or "en, pt") in addition
  to a single code; empty/missing keeps the "allow all" semantics.
"""
import json
from unittest.mock import patch, MagicMock
import pytest

import dredger


def test_sites_env_accepts_comma_separated_urls(monkeypatch):
    monkeypatch.setenv("SITES", "https://a.example, https://b.example,https://c.example")
    monkeypatch.chdir("/tmp")  # no sites.json here
    result = dredger.load_sites_from_source(None)
    assert result == ["https://a.example", "https://b.example", "https://c.example"]


def test_sites_env_accepts_file_path(tmp_path, monkeypatch):
    p = tmp_path / "my_sites.json"
    p.write_text(json.dumps({"sites": ["https://x.example", "https://y.example"]}))
    monkeypatch.setenv("SITES", str(p))
    monkeypatch.chdir(tmp_path)
    result = dredger.load_sites_from_source(None)
    assert result == ["https://x.example", "https://y.example"]


def test_sites_env_file_path_with_array_format(tmp_path, monkeypatch):
    p = tmp_path / "sites_arr.json"
    p.write_text(json.dumps(["https://only.example"]))
    monkeypatch.setenv("SITES", str(p))
    monkeypatch.chdir(tmp_path)
    assert dredger.load_sites_from_source(None) == ["https://only.example"]


# --- Language filter ---

def test_parse_language_filter_single_code():
    assert dredger.parse_language_filter("en") == ["en"]


def test_parse_language_filter_multiple_codes_no_space():
    assert dredger.parse_language_filter("en,pt") == ["en", "pt"]


def test_parse_language_filter_multiple_codes_with_spaces():
    assert dredger.parse_language_filter("en, pt , es") == ["en", "pt", "es"]


def test_parse_language_filter_quoted_form():
    # Users may quote in .env: LANGUAGE_FILTER="en, pt"
    assert dredger.parse_language_filter('"en, pt"') == ["en", "pt"]
    assert dredger.parse_language_filter("'en,pt'") == ["en", "pt"]


def test_parse_language_filter_empty_means_allow_all():
    assert dredger.parse_language_filter("") == []
    assert dredger.parse_language_filter("   ") == []


def test_parse_language_filter_normalizes_case():
    assert dredger.parse_language_filter("EN, Pt") == ["en", "pt"]


def test_verifier_accepts_when_lang_matches_any(monkeypatch):
    monkeypatch.setattr(dredger, "LANGUAGE_FILTER", ["en", "pt"])
    body_str = (
        '<html lang="pt"><body><div class="wp-recipe-maker">'
        'Misture os ingredientes secos em uma tigela grande. '
        'Adicione os ovos e bata bem até ficar homogêneo. '
        'Asse no forno por trinta minutos.</div></body></html>'
    )
    session = MagicMock()
    session.get.return_value = MagicMock(
        status_code=200, text=body_str, content=body_str.encode("utf-8"),
    )
    v = dredger.RecipeVerifier(session)
    is_recipe, _, error = v.verify_recipe("https://example.com/receita")
    assert is_recipe is True, f"Portuguese recipe should pass when filter includes pt; got error={error}"


def test_verifier_rejects_when_lang_not_in_filter(monkeypatch):
    monkeypatch.setattr(dredger, "LANGUAGE_FILTER", ["en", "pt"])
    # German body, filter only allows en+pt
    body = ('<html><body><div class="wp-recipe-maker">'
            'Mehl und Zucker in einer Schüssel vermischen. '
            'Die Eier hinzufügen und gut verrühren. '
            'Backen Sie den Kuchen für dreißig Minuten im Ofen.</div></body></html>').encode("utf-8")
    session = MagicMock()
    session.get.return_value = MagicMock(status_code=200, text=body.decode("utf-8"), content=body)
    v = dredger.RecipeVerifier(session)
    is_recipe, _, error = v.verify_recipe("https://example.com/rezept")
    assert is_recipe is False
    assert "Language mismatch" in (error or "")


def test_verifier_allows_all_when_filter_empty(monkeypatch):
    monkeypatch.setattr(dredger, "LANGUAGE_FILTER", [])
    body = b'<html><body><div class="wp-recipe-maker">Anything</div></body></html>'
    session = MagicMock()
    session.get.return_value = MagicMock(status_code=200, text=body.decode("utf-8"), content=body)
    v = dredger.RecipeVerifier(session)
    is_recipe, _, _ = v.verify_recipe("https://example.com/r")
    assert is_recipe is True
