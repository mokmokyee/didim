from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_frontend_uses_direct_gemini_keyword_mapping():
    adapter = (ROOT / "public" / "js" / "api.js").read_text(encoding="utf-8")
    assert "../data/search_taxonomy.json" in adapter
    assert "resolveSearchQuery" in adapter
    assert "matchesResolvedSearch" in adapter
    assert "generativelanguage.googleapis.com" in adapter
    assert '"x-goog-api-key"' in adapter
    assert "responseJsonSchema" in adapter
    assert "gemini-runtime-config.js" in adapter
    assert "firebase-ai.js" not in adapter
    assert "firebase-firestore.js" in adapter
    assert '"catalog", "opportunities"' in adapter


def test_firebase_hosting_and_security_rules_are_present():
    assert (ROOT / "firebase.json").is_file()
    rules = (ROOT / "firestore.rules").read_text(encoding="utf-8")
    assert "request.auth.uid == uid" in rules
    assert "allow write: if false" in rules


def test_search_taxonomy_and_browser_resolver_are_deployed():
    assert (ROOT / "public" / "data" / "search_taxonomy.json").is_file()
    assert (ROOT / "public" / "js" / "search-resolver.js").is_file()
    page = (ROOT / "public" / "programs.html").read_text(encoding="utf-8")
    assert "js/search-resolver.js" in page


def test_service_credentials_are_ignored():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "firebase-service-account*.json" in ignored
    assert ".env" in ignored
    assert "public/js/gemini-runtime-config.js" in ignored


def test_deploy_generates_browser_gemini_config_from_secret():
    workflow = (ROOT / ".github" / "workflows" / "deploy-hosting.yml").read_text(encoding="utf-8")
    writer = (ROOT / "scripts" / "write-gemini-runtime-config.mjs").read_text(encoding="utf-8")
    assert "secrets.GEMINI_API_KEY" in workflow
    assert "npm run gemini-runtime:write" in workflow
    assert "process.env.GEMINI_API_KEY" in writer
