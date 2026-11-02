"""Portable Everything/ES installer helpers (no network, no process start)."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from winbrow import everything  # noqa: E402


def test_app_dir_override(tmp_path, monkeypatch):
    monkeypatch.setenv("WINBROW_EVERYTHING_DIR", str(tmp_path))
    assert everything.app_dir() == tmp_path.resolve()
    assert everything.es_path() == tmp_path.resolve() / "es.exe"
    assert everything.everything_path() == tmp_path.resolve() / "Everything.exe"


def test_fixed_drive_override(monkeypatch):
    monkeypatch.setenv("WINBROW_EVERYTHING_FOLDERS", "C:\\;D:\\")
    assert everything._fixed_drive_roots() == ["C:\\", "D:\\"]


def test_disabled_install_does_not_touch_disk(tmp_path, monkeypatch):
    monkeypatch.setenv("WINBROW_EVERYTHING_DIR", str(tmp_path))
    result = everything.ensure_everything(auto_install=False)
    assert result["ok"] is False
    assert result["status"] == "missing"
    assert not (tmp_path / "es.exe").exists()


def test_unsupported_architecture_is_rejected(monkeypatch):
    monkeypatch.setattr(everything.platform, "machine", lambda: "arm64")
    result = everything.ensure_everything(auto_install=True)
    assert result["ok"] is False
    assert result["status"] == "unsupported_arch"


def test_safe_extract_only_takes_exact_root_members(tmp_path):
    archive = tmp_path / "test.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("es.exe", b"fake exe")
        zf.writestr("nested/evil.exe", b"nope")
        zf.writestr("Everything.exe", b"fake everything")
    out = tmp_path / "out"
    out.mkdir()
    everything._safe_extract(archive, ("es.exe",), out)
    assert (out / "es.exe").read_bytes() == b"fake exe"
    assert not (out / "Everything.exe").exists()

    try:
        everything._safe_extract(archive, ("nested/evil.exe",), out)
    except RuntimeError:
        pass
    else:
        raise AssertionError("nested members must be rejected")
    assert not (out / "evil.exe").exists()
