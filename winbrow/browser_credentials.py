"""
Consent-based browser password import
=====================================

This module never reads a browser profile. It accepts a CSV that the user
exported from the browser's own password manager, shows a preview without
secrets, and stores only the rows the user explicitly selects. Passwords are
encrypted with Windows DPAPI before they touch disk and are never returned by
the public API.

The internal ``get_credential_for_origin`` helper is for a future credential
broker. Callers must not serialize or log its result.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import os
import re
import secrets
import subprocess
import time
from pathlib import Path
from threading import RLock
from typing import Any
from urllib.parse import urlsplit

from .integrations import _dpapi_protect, _dpapi_unprotect

log = logging.getLogger("winbrow.browser_credentials")

DEFAULT_STORE = Path(__file__).resolve().parent.parent / "data" / "browser_credentials.json"
STORE_VERSION = 1

MAX_CSV_BYTES = 5 * 1024 * 1024
MAX_IMPORT_ROWS = 5000
PENDING_TTL_S = 600.0

_LOCK = RLock()
_PENDING: dict[str, dict[str, Any]] = {}


class CredentialImportError(ValueError):
    """A user-correctable problem with the selected CSV or import request."""


# ---------------------------------------------------------------------------
# Secure storage
# ---------------------------------------------------------------------------

def _store_path() -> Path:
    override = os.environ.get("WINBROW_CREDENTIALS_PATH")
    return Path(override).expanduser().resolve() if override else DEFAULT_STORE


def _load_store() -> dict[str, Any]:
    path = _store_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"version": STORE_VERSION, "credentials": {}}
    except Exception as exc:
        log.warning("Corrupt browser credential store ignored: %s", exc)
        return {"version": STORE_VERSION, "credentials": {}}
    if not isinstance(data, dict):
        return {"version": STORE_VERSION, "credentials": {}}
    data.setdefault("version", STORE_VERSION)
    if not isinstance(data.get("credentials"), dict):
        data["credentials"] = {}
    return data


def _save_store(data: dict[str, Any]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)
    if os.name == "nt":
        user = os.environ.get("USERNAME", "")
        if user:
            try:
                # Best effort: the DPAPI blob is already user-bound, but a
                # private ACL prevents other local users from copying the file.
                subprocess.run(
                    ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:F"],
                    check=False,
                    capture_output=True,
                    timeout=10,
                )
            except Exception as exc:
                log.debug("Could not tighten credential-store ACL: %s", exc)


def _protect_password(password: str) -> str:
    token = _dpapi_protect(password)
    if not token.startswith("dpapi:"):
        raise CredentialImportError(
            "Windows DPAPI is unavailable; refusing to store passwords in plaintext."
        )
    return token


def _unprotect_password(token: str) -> str:
    if not token.startswith("dpapi:"):
        raise CredentialImportError("Stored credential is not DPAPI-protected.")
    value = _dpapi_unprotect(token)
    if not value:
        raise CredentialImportError("Could not decrypt the stored credential.")
    return value


def _credential_id(origin: str, username: str) -> str:
    raw = f"{origin}\0{username.casefold()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------

def _clean_source(source: str) -> str:
    value = re.sub(r"[^a-z0-9_-]", "", str(source or "").strip().lower())
    return value[:32] or "browser"


def _origin_from_url(raw: str) -> tuple[str, str]:
    """Return (origin, safe login URL) from a Chromium password CSV row."""
    url = str(raw or "").strip()
    if not url:
        raise CredentialImportError("A CSV row is missing its URL.")
    if "://" not in url:
        url = "https://" + url
    parsed = urlsplit(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise CredentialImportError("Only http:// and https:// logins can be imported.")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise CredentialImportError("A CSV row has an invalid URL.")
    if ":" not in host:
        try:
            # Store/display an ASCII origin so Unicode lookalikes cannot hide
            # the real host in the import picker.
            host = host.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise CredentialImportError("A CSV row has an invalid hostname.") from exc
    try:
        port = parsed.port
    except ValueError as exc:
        raise CredentialImportError("A CSV row has an invalid port.") from exc
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    default_port = 80 if scheme == "http" else 443
    netloc = host if port in (None, default_port) else f"{host}:{port}"
    origin = f"{scheme}://{netloc}"
    path = parsed.path or "/"
    if len(path) > 512:
        path = "/"
    # Strip query strings and fragments: they often contain session tokens.
    return origin, f"{origin}{path}"


def _header_map(fieldnames: list[str] | None) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for name in fieldnames or []:
        key = str(name or "").lstrip("\ufeff").strip().lower()
        if key:
            mapping[key] = name
    return mapping


def parse_browser_csv(
    text: str,
    source: str = "browser",
    stats: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Parse a Chromium password export and return selected-row candidates.

    The returned dicts contain plaintext passwords in memory. They are used
    only by the pending import and the commit path; public serializers must not
    include them. Rows with an unsupported URL are skipped and counted in
    ``stats["skipped"]``.
    """
    raw_text = str(text or "")
    if not raw_text.strip():
        raise CredentialImportError("The selected file is empty.")
    if len(raw_text.encode("utf-8", "surrogatepass")) > MAX_CSV_BYTES:
        raise CredentialImportError("The selected CSV is larger than 5 MB.")

    reader = csv.DictReader(io.StringIO(raw_text, newline=""))
    headers = _header_map(reader.fieldnames)
    required = ("url", "username", "password")
    missing = [name for name in required if name not in headers]
    if missing:
        raise CredentialImportError(
            "This is not a Chrome/Brave password export. Expected columns: "
            "name, url, username, password, note."
        )

    source_name = _clean_source(source)
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    skipped = 0
    for row in reader:
        if len(by_key) >= MAX_IMPORT_ROWS:
            raise CredentialImportError(
                f"The CSV has more than {MAX_IMPORT_ROWS} unique logins; import a smaller export."
            )
        url = str(row.get(headers["url"]) or "").strip()
        username = str(row.get(headers["username"]) or "").strip()
        password = str(row.get(headers["password"]) or "")
        if not username or not password:
            skipped += 1
            continue
        try:
            origin, login_url = _origin_from_url(url)
        except CredentialImportError:
            skipped += 1
            continue
        name = str(row.get(headers.get("name", "")) or "").strip()[:120]
        key = (origin, username.casefold())
        by_key[key] = {
            "origin": origin,
            "url": login_url,
            "username": username[:320],
            "password": password,
            "name": name,
            "source": source_name,
            "has_password": True,
        }

    if stats is not None:
        stats["skipped"] = skipped
    if not by_key:
        raise CredentialImportError(
            "No rows with a supported http(s) URL, username, and password were found."
        )
    return list(by_key.values())


# ---------------------------------------------------------------------------
# Preview / commit
# ---------------------------------------------------------------------------

def _prune_pending(now: float) -> None:
    for token, item in list(_PENDING.items()):
        if now - float(item.get("created", 0)) > PENDING_TTL_S:
            _PENDING.pop(token, None)


def _public_entry(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["id"],
        "origin": item["origin"],
        "username": item["username"],
        "name": item.get("name", ""),
        "source": item.get("source", "browser"),
        "has_password": True,
    }


def preview_browser_csv(text: str, source: str = "browser") -> dict[str, Any]:
    """Parse the CSV and return metadata only. No password is serialized."""
    stats: dict[str, int] = {}
    items = parse_browser_csv(text, source, stats=stats)
    for item in items:
        item["id"] = secrets.token_hex(8)
    token = secrets.token_urlsafe(24)
    now = time.time()
    with _LOCK:
        _prune_pending(now)
        _PENDING[token] = {"created": now, "items": items}
    return {
        "import_id": token,
        "count": len(items),
        "skipped": stats.get("skipped", 0),
        "source": _clean_source(source),
        "entries": [_public_entry(item) for item in items],
    }


def cancel_browser_import(import_id: str) -> bool:
    with _LOCK:
        return _PENDING.pop(str(import_id or ""), None) is not None


def commit_browser_import(import_id: str, ids: list[str]) -> dict[str, Any]:
    """Store only the selected rows, encrypted. Returns metadata only."""
    token = str(import_id or "").strip()
    selected = {str(item) for item in (ids or []) if str(item).strip()}
    if not token:
        raise CredentialImportError("Missing import session. Preview the CSV again.")
    if not selected:
        raise CredentialImportError("Select at least one login to import.")

    with _LOCK:
        now = time.time()
        _prune_pending(now)
        pending = _PENDING.get(token)
        if not pending:
            raise CredentialImportError("Import session expired. Preview the CSV again.")
        items = [item for item in pending["items"] if item["id"] in selected]
        if not items:
            raise CredentialImportError("None of the selected logins are in this import session.")

        data = _load_store()
        credentials = data.setdefault("credentials", {})
        for item in items:
            cid = _credential_id(item["origin"], item["username"])
            credentials[cid] = {
                "origin": item["origin"],
                "url": item["url"],
                "username": item["username"],
                "name": item.get("name", ""),
                "source": item.get("source", "browser"),
                "password": _protect_password(item["password"]),
                "imported_at": now,
            }
        _save_store(data)
        _PENDING.pop(token, None)
        log.info(
            "Imported %d browser login(s) from %s into the local DPAPI vault",
            len(items), items[0].get("source", "browser"),
        )

    return {
        "imported": len(items),
        "credentials": list_credentials()["credentials"],
    }


# ---------------------------------------------------------------------------
# Public reads / deletes
# ---------------------------------------------------------------------------

def _public_credential(cid: str, item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": cid,
        "origin": str(item.get("origin") or ""),
        "username": str(item.get("username") or ""),
        "name": str(item.get("name") or ""),
        "source": str(item.get("source") or "browser"),
        "imported_at": item.get("imported_at", 0),
        "has_password": bool(item.get("password")),
    }


def list_credentials() -> dict[str, Any]:
    with _LOCK:
        data = _load_store()
        entries = [
            _public_credential(cid, item)
            for cid, item in data.get("credentials", {}).items()
        ]
    entries.sort(key=lambda item: (item["origin"], item["username"].casefold()))
    return {"credentials": entries, "count": len(entries)}


def delete_credential(credential_id: str) -> bool:
    cid = str(credential_id or "").strip()
    if not cid:
        return False
    with _LOCK:
        data = _load_store()
        credentials = data.get("credentials", {})
        if cid not in credentials:
            return False
        credentials.pop(cid, None)
        _save_store(data)
    return True


def clear_credentials() -> int:
    with _LOCK:
        data = _load_store()
        removed = len(data.get("credentials", {}))
        data["credentials"] = {}
        _save_store(data)
    return removed


def get_credential_for_origin(origin: str, username: str = "") -> dict[str, Any] | None:
    """Internal broker helper. Never serialize this result to the model or logs."""
    wanted_origin = str(origin or "").strip().rstrip("/")
    wanted_user = str(username or "").strip().casefold()
    with _LOCK:
        data = _load_store()
        for cid, item in data.get("credentials", {}).items():
            if str(item.get("origin") or "").rstrip("/") != wanted_origin:
                continue
            if wanted_user and str(item.get("username") or "").casefold() != wanted_user:
                continue
            return {
                "id": cid,
                "origin": str(item.get("origin") or ""),
                "username": str(item.get("username") or ""),
                "password": _unprotect_password(str(item.get("password") or "")),
            }
    return None
