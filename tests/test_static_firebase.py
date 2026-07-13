from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_frontend_uses_firebase_without_flask_api_calls():
    adapter = (ROOT / "public" / "js" / "api.js").read_text(encoding="utf-8")
    assert "/api/" not in adapter
    assert "firebase-firestore.js" in adapter
    assert '"catalog", "opportunities"' in adapter


def test_firebase_hosting_and_security_rules_are_present():
    assert (ROOT / "firebase.json").is_file()
    rules = (ROOT / "firestore.rules").read_text(encoding="utf-8")
    assert "request.auth.uid == uid" in rules
    assert "allow write: if false" in rules


def test_service_credentials_are_ignored():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "firebase-service-account*.json" in ignored
    assert ".env" in ignored
