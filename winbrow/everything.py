"""Optional portable Everything + ES search backend.

``find_files`` uses the Everything CLI (``es.exe``) as its primary filename
search. This module makes that backend available on machines where Everything
is not installed:

* downloads the official voidtools portable Everything and ES zips;
* verifies both SHA-256 digests and the Authenticode signatures;
* extracts only ``Everything.exe``, ``Everything.lng`` and ``es.exe``;
* starts a private Everything instance (``WinBrow``) with folder indexes for
  fixed drives, using the current user's profile (no service/admin required).

The instance is intentionally separate from a user's normal Everything
instance. If anything fails, ``find_files`` reports that the Everything index
is not ready instead of falling back to a folder walk or Windows Search.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import logging
import os
import platform
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

log = logging.getLogger("winbrow.everything")

INSTANCE = "WinBrow"
EVERYTHING_VERSION = "1.5.0.1424b"
ES_VERSION = "1.1.0.38"

# Official voidtools downloads. Everything's digest is the published value;
# ES is pinned to the digest of the official x64 archive and every extracted
# executable is additionally checked with Authenticode.
EVERYTHING_URL = (
    f"https://www.voidtools.com/Everything-{EVERYTHING_VERSION}.x64.zip"
)
EVERYTHING_SHA256 = "f8e5d907305fc1aff288ad4d722548f36a1ef8c3389933b1fbc935dba7083084"
ES_URL = f"https://www.voidtools.com/ES-{ES_VERSION}.x64.zip"
ES_SHA256 = "5e0c70cbf4f694080c34aa7c6c745e606c16fe76a4b5423b93ebf9dc34274c99"

_FIXED_DRIVE = 3
_DOWNLOAD_TIMEOUT_S = 90
_INSTALL_LOCK = ".install.lock"


def app_dir() -> Path:
    override = os.environ.get("WINBROW_EVERYTHING_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "WinBrow" / "Everything"


def es_path() -> Path:
    return app_dir() / "es.exe"


def everything_path() -> Path:
    return app_dir() / "Everything.exe"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _download(url: str, destination: Path) -> None:
    request = Request(url, headers={"User-Agent": "WinBrow/3 Everything setup"})
    with urlopen(request, timeout=_DOWNLOAD_TIMEOUT_S) as response:
        status = int(getattr(response, "status", 200))
        if status != 200:
            raise RuntimeError(f"HTTP {status} downloading {url}")
        with destination.open("wb") as handle:
            shutil.copyfileobj(response, handle, length=1024 * 1024)


def _safe_extract(zip_path: Path, members: tuple[str, ...], destination: Path) -> None:
    """Extract only exact root-level members; reject traversal/other files."""
    with zipfile.ZipFile(zip_path) as archive:
        names = {
            info.filename.replace("\\", "/"): info
            for info in archive.infolist()
        }
        for wanted in members:
            info = names.get(wanted)
            if info is None or not info.filename or "/" in info.filename:
                raise RuntimeError(f"{zip_path.name} is missing {wanted}")
            target = destination / wanted
            with archive.open(info) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)


def _signed_by_voidtools(path: Path) -> bool:
    if os.name != "nt":
        return False
    escaped = str(path).replace("'", "''")
    script = (
        f"$s = Get-AuthenticodeSignature -LiteralPath '{escaped}'; "
        "if ($s.Status -ne 'Valid') { exit 1 }; "
        "if ($s.SignerCertificate.Subject -notmatch 'voidtools') { exit 2 }; "
        "exit 0"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as exc:
        log.debug("Authenticode check failed for %s: %s", path, exc)
        return False
    return result.returncode == 0


def _install() -> dict[str, Any]:
    target_dir = app_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    lock = target_dir / _INSTALL_LOCK
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            stale = time.time() - lock.stat().st_mtime > 600
            if not stale:
                return {"ok": True, "status": "install_in_progress"}
            lock.unlink(missing_ok=True)
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except Exception:
            return {"ok": True, "status": "install_in_progress"}
    os.close(fd)

    try:
        with tempfile.TemporaryDirectory(prefix="winbrow-everything-") as raw_tmp:
            tmp = Path(raw_tmp)
            everything_zip = tmp / "Everything.zip"
            es_zip = tmp / "ES.zip"
            payload = tmp / "payload"
            payload.mkdir()

            _download(EVERYTHING_URL, everything_zip)
            _download(ES_URL, es_zip)
            for path, expected, label in (
                (everything_zip, EVERYTHING_SHA256, "Everything"),
                (es_zip, ES_SHA256, "ES"),
            ):
                actual = _sha256(path)
                if actual.lower() != expected.lower():
                    raise RuntimeError(
                        f"{label} download SHA-256 mismatch: {actual} != {expected}"
                    )

            _safe_extract(
                everything_zip, ("Everything.exe", "Everything.lng"), payload)
            _safe_extract(es_zip, ("es.exe",), payload)
            for name in ("Everything.exe", "es.exe"):
                if not _signed_by_voidtools(payload / name):
                    raise RuntimeError(f"{name} is not signed by voidtools")

            for name in ("Everything.exe", "Everything.lng", "es.exe"):
                os.replace(payload / name, target_dir / name)

            manifest = {
                "everything_version": EVERYTHING_VERSION,
                "es_version": ES_VERSION,
                "source": "https://www.voidtools.com/",
                "installed_at": time.time(),
            }
            (target_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2), encoding="utf-8")
        log.info("Installed portable Everything + ES in %s", target_dir)
        return {"ok": True, "status": "installed", "path": str(target_dir)}
    finally:
        try:
            lock.unlink(missing_ok=True)
        except OSError:
            pass


def _fixed_drive_roots() -> list[str]:
    override = os.environ.get("WINBROW_EVERYTHING_FOLDERS", "").strip()
    if override:
        return [part.strip() for part in override.split(";") if part.strip()]
    if os.name != "nt":
        return []
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.GetLogicalDrives.restype = ctypes.c_uint
        kernel32.GetDriveTypeW.argtypes = [ctypes.c_wchar_p]
        kernel32.GetDriveTypeW.restype = ctypes.c_uint
        mask = int(kernel32.GetLogicalDrives())
    except Exception as exc:
        log.debug("Could not enumerate drives: %s", exc)
        return []
    roots: list[str] = []
    for index, letter in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
        if not mask & (1 << index):
            continue
        root = f"{letter}:\\"
        try:
            if int(kernel32.GetDriveTypeW(root)) == _FIXED_DRIVE:
                roots.append(root)
        except Exception:
            continue
    return roots


def _ipc_ready() -> bool:
    """True when the private Everything instance has an IPC endpoint."""
    cli = es_path()
    if not cli.is_file():
        return False
    try:
        result = subprocess.run(
            [str(cli), "-instance", INSTANCE, "-get-everything-version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return False
    return result.returncode == 0


def _search_ready() -> bool:
    """True when ES can run a query (initial folder indexing may still be busy)."""
    cli = es_path()
    if not cli.is_file():
        return False
    try:
        result = subprocess.run(
            [
                str(cli), "-instance", INSTANCE, "-timeout", "1500",
                "-n", "1", "__winbrow_ready_probe__",
            ],
            capture_output=True,
            text=True,
            timeout=6,
        )
    except Exception:
        return False
    return result.returncode == 0


def _start() -> bool:
    exe = everything_path()
    if not exe.is_file():
        return False
    if _ipc_ready():
        return True

    directory = app_dir()
    config = directory / "Everything.ini"
    folders_file = directory / "folders.txt"
    folders = _fixed_drive_roots()
    folder_text = ";".join(folders)
    args = [
        str(exe),
        "-instance", INSTANCE,
        "-startup",
        "-config", str(config),
    ]
    previous = ""
    try:
        previous = folders_file.read_text(encoding="utf-8").strip()
    except OSError:
        pass
    if folders and (not config.is_file() or previous != folder_text):
        args.extend(["-no-auto-index", "-folders", folder_text])

    try:
        subprocess.Popen(
            args,
            cwd=str(directory),
            close_fds=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        log.warning("Could not start Everything: %s", exc)
        return False

    # IPC readiness is enough; the initial folder scan may continue in the
    # background. ES waits for the database with -timeout at query time.
    for _ in range(30):
        time.sleep(0.5)
        if _ipc_ready():
            if folders:
                try:
                    folders_file.write_text(folder_text, encoding="utf-8")
                except OSError:
                    pass
            return True
    log.warning("Everything did not expose its IPC endpoint in time")
    return False


def ensure_everything(auto_install: bool | None = None) -> dict[str, Any]:
    """Install (if allowed) and start the private Everything instance.

    Safe to call from a background thread at application startup. Returns a
    status dict; never raises for normal download/start failures.
    """
    if os.name != "nt":
        return {"ok": False, "status": "unsupported"}
    machine = platform.machine().lower()
    if machine not in {"amd64", "x86_64"}:
        return {"ok": False, "status": "unsupported_arch", "arch": machine}
    if auto_install is None:
        auto_install = os.environ.get(
            "WINBROW_EVERYTHING_AUTOINSTALL", "1"
        ).strip().lower() not in {"0", "false", "no", "off"}

    if not es_path().is_file() or not everything_path().is_file():
        if not auto_install:
            return {
                "ok": False,
                "status": "missing",
                "es_path": str(es_path()),
                "everything_path": str(everything_path()),
            }
        try:
            _install()
        except Exception as exc:
            log.warning("Everything install failed (non-fatal): %s", exc)
            return {"ok": False, "status": "install_failed", "error": str(exc)}

    started = _start()
    if not started:
        return {
            "ok": False,
            "status": "start_failed",
            "es_path": str(es_path()),
            "everything_path": str(everything_path()),
        }
    # IPC is up as soon as the process starts; a first-run folder scan can
    # still be building, so distinguish "ready" from "indexing".
    ready = _search_ready()
    return {
        "ok": True,
        "status": "ready" if ready else "indexing",
        "es_path": str(es_path()),
        "everything_path": str(everything_path()),
    }
