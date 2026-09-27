import json

from evidencegate.api import app as api_app


def test_packaged_release_is_stable_when_current_source_sha_changes(tmp_path, monkeypatch):
    static = tmp_path / "static"
    static.mkdir()
    (static / "release-manifest.json").write_text(json.dumps({
        "release_id": "REL-A", "source_sha": "SHA-A", "built_at": "2026-09-01T00:00:00Z",
    }), encoding="utf-8")
    monkeypatch.setattr(api_app, "STATIC_ROOT", static)
    monkeypatch.setenv("EVIDENCEGATE_BUILD_SHA", "SHA-B")
    monkeypatch.setenv("EVIDENCEGATE_RELEASE_ID", "REL-B")

    assert api_app.release_metadata() == {
        "release_id": "REL-A", "source_sha": "SHA-A", "api_contract_version": "1",
    }
