"""Consent-based browser CSV import: parsing, DPAPI storage, and API masking."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from winbrow import browser_credentials as creds  # noqa: E402

CSV_TEXT = """name,url,username,password,note
jecc,https://jecc.etlab.in/login,student@example.com,super-secret,
example,https://example.com/,bob,hunter2,
duplicate,https://jecc.etlab.in/other,student@example.com,new-secret,
"""


@pytest.fixture()
def store(tmp_path, monkeypatch):
    path = tmp_path / "browser_credentials.json"
    monkeypatch.setenv("WINBROW_CREDENTIALS_PATH", str(path))
    return path


def test_preview_returns_metadata_only(store):
    preview = creds.preview_browser_csv(CSV_TEXT, "brave")

    assert preview["count"] == 2
    assert preview["import_id"]
    assert [entry["origin"] for entry in preview["entries"]] == [
        "https://jecc.etlab.in",
        "https://example.com",
    ]
    rendered = json.dumps(preview)
    assert "super-secret" not in rendered
    assert "new-secret" not in rendered
    assert "hunter2" not in rendered
    assert '"password":' not in rendered


def test_commit_encrypts_only_selected_rows(store):
    preview = creds.preview_browser_csv(CSV_TEXT, "brave")
    jecc = next(item for item in preview["entries"] if item["origin"] == "https://jecc.etlab.in")

    result = creds.commit_browser_import(preview["import_id"], [jecc["id"]])

    assert result["imported"] == 1
    assert "super-secret" not in json.dumps(result)
    assert "new-secret" not in json.dumps(result)
    raw = store.read_text(encoding="utf-8")
    assert "super-secret" not in raw
    assert "new-secret" not in raw
    assert "hunter2" not in raw
    assert "dpapi:" in raw

    listed = creds.list_credentials()
    assert listed["count"] == 1
    assert listed["credentials"][0]["origin"] == "https://jecc.etlab.in"
    assert listed["credentials"][0]["has_password"] is True
    assert '"password":' not in json.dumps(listed)

    internal = creds.get_credential_for_origin("https://jecc.etlab.in")
    assert internal is not None
    assert internal["password"] == "new-secret"

    assert creds.delete_credential(listed["credentials"][0]["id"]) is True
    assert creds.list_credentials()["count"] == 0


def test_commit_requires_a_selection(store):
    preview = creds.preview_browser_csv(CSV_TEXT, "brave")
    with pytest.raises(creds.CredentialImportError):
        creds.commit_browser_import(preview["import_id"], [])


def test_cancel_discards_the_pending_plaintext(store):
    preview = creds.preview_browser_csv(CSV_TEXT, "brave")
    assert creds.cancel_browser_import(preview["import_id"]) is True
    with pytest.raises(creds.CredentialImportError):
        creds.commit_browser_import(preview["import_id"], [preview["entries"][0]["id"]])


def test_reimport_updates_the_same_origin_and_username(store):
    first = creds.preview_browser_csv(
        "name,url,username,password,note\nx,https://site.test/,me,old,\n", "brave")
    creds.commit_browser_import(first["import_id"], [first["entries"][0]["id"]])

    second = creds.preview_browser_csv(
        "name,url,username,password,note\nx,https://site.test/login,me,new,\n", "chrome")
    result = creds.commit_browser_import(second["import_id"], [second["entries"][0]["id"]])

    assert result["imported"] == 1
    assert creds.list_credentials()["count"] == 1
    assert creds.get_credential_for_origin("https://site.test/")["password"] == "new"


def test_rejects_wrong_csv_and_non_http_urls(store):
    with pytest.raises(creds.CredentialImportError):
        creds.preview_browser_csv("url,username\nhttps://x.test,a\n", "brave")

    with pytest.raises(creds.CredentialImportError):
        creds.preview_browser_csv(
            "name,url,username,password\nx,javascript:alert(1),me,pw\n", "brave")


def test_skips_unsupported_rows_but_keeps_valid_ones(store):
    preview = creds.preview_browser_csv(
        "name,url,username,password\n"
        "bad,android://app/,me,pw\n"
        "good,https://site.test/,me,ok\n",
        "brave",
    )
    assert preview["count"] == 1
    assert preview["skipped"] == 1
    assert preview["entries"][0]["origin"] == "https://site.test"


def test_api_masks_secrets_and_deletes(store):
    from server import app

    client = TestClient(app)
    preview_resp = client.post(
        "/api/browser-credentials/preview",
        json={"csv": CSV_TEXT, "source": "brave"},
    )
    assert preview_resp.status_code == 200
    assert "super-secret" not in preview_resp.text
    preview = preview_resp.json()
    jecc = next(item for item in preview["entries"] if item["origin"] == "https://jecc.etlab.in")

    import_resp = client.post(
        "/api/browser-credentials/import",
        json={"import_id": preview["import_id"], "ids": [jecc["id"]]},
    )
    assert import_resp.status_code == 200
    assert "super-secret" not in import_resp.text
    assert import_resp.json()["imported"] == 1

    list_resp = client.get("/api/browser-credentials")
    assert list_resp.status_code == 200
    assert "super-secret" not in list_resp.text
    assert '"password":' not in list_resp.text
    cid = list_resp.json()["credentials"][0]["id"]

    assert client.delete(f"/api/browser-credentials/{cid}").status_code == 200
    assert client.delete(f"/api/browser-credentials/{cid}").status_code == 404


def test_api_rejects_bad_csv(store):
    from server import app

    client = TestClient(app)
    resp = client.post(
        "/api/browser-credentials/preview",
        json={"csv": "not,a,password,csv\n1,2,3,4\n", "source": "brave"},
    )
    assert resp.status_code == 400
    assert "Chrome/Brave" in resp.json()["error"]


def test_ui_exposes_the_consented_import_flow():
    from server import app

    client = TestClient(app)
    html = client.get("/").text
    assert 'id="passwordsBtn"' in html
    assert 'id="browserCredsModal"' in html
    assert 'id="browserCredsFile"' in html
    assert "openBrowserCreds" in html
    assert "previewBrowserCreds" in html
