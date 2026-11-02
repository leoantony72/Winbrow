"""Write policy: user content may go anywhere except OS-owned system trees.

The planner and the user can name any folder (another drive, a project folder,
a network share). Only Windows/Program Files-class locations are refused, so a
typo or a hostile page cannot drop files into System32.
"""

from __future__ import annotations

import os
from pathlib import Path

_ENV_ROOTS = (
    "SystemRoot",
    "windir",
    "ProgramFiles",
    "ProgramFiles(x86)",
    "ProgramW6432",
    "ProgramData",
    "ALLUSERSPROFILE",
)
_EXTRA_ROOTS = (
    r"C:\System Volume Information",
    r"C:\$Recycle.Bin",
    r"C:\Recovery",
    r"C:\Boot",
    r"C:\EFI",
    r"C:\PerfLogs",
    r"C:\Config.Msi",
    r"C:\Documents and Settings",
    r"C:\Windows.old",
)

# Standard user folders. A relative path starting with one of these names must
# resolve under the real user profile, never under the app's process cwd.
USER_FOLDER_NAMES = frozenset(
    {"desktop", "documents", "downloads", "pictures", "music", "videos"}
)


def project_root() -> Path:
    """The WinBrow source/install directory (never a deliverable location)."""
    return Path(__file__).resolve().parent.parent


def remap_project_user_folder(path: object) -> Path:
    """Move ``<project>\\Desktop\\x`` back to the real ``%USERPROFILE%\\Desktop\\x``.

    Planner/skill subprocesses sometimes build a user-folder path from the
    process cwd, producing paths such as
    ``D:\\Codee\\desktop_agent\\Desktop\\deck``. That is never a user
    deliverable, so only the well-known first component is remapped. Ordinary
    project paths (``<project>\\src\\...``) are left untouched.
    """
    candidate = Path(path)
    if not candidate.is_absolute():
        return candidate
    try:
        relative = candidate.resolve().relative_to(project_root())
    except (OSError, ValueError):
        return candidate
    parts = relative.parts
    if parts and str(parts[0]).lower() in USER_FOLDER_NAMES:
        return Path(os.path.expanduser("~")) / parts[0] / Path(*parts[1:])
    return candidate


def _norm(value: object) -> str:
    try:
        text = os.path.expandvars(os.path.expanduser(str(value)))
        return os.path.normcase(os.path.abspath(text)).rstrip("\\/")
    except Exception:
        return os.path.normcase(str(value)).rstrip("\\/")


def protected_roots() -> tuple[str, ...]:
    """Normalized system-owned roots for this machine."""
    roots: list[str] = []
    for variable in _ENV_ROOTS:
        value = os.environ.get(variable)
        if value:
            roots.append(_norm(value))
    roots.extend(_norm(path) for path in _EXTRA_ROOTS)
    return tuple(dict.fromkeys(root for root in roots if root))


def is_protected_path(path: object) -> bool:
    """True when ``path`` is a Windows/Program Files system location."""
    target = _norm(path)
    if not target:
        return False
    separator = os.sep
    for root in protected_roots():
        if target == root or target.startswith(root + separator):
            return True
    return False


def write_refusal(path: object) -> str:
    """Return a planner-facing refusal message, or an empty string when allowed."""
    if not is_protected_path(path):
        return ""
    return (
        f"Refusing to write inside the Windows system area: {path}. "
        "Choose a folder under the user profile, another drive, or a project "
        "folder instead."
    )


def explicit_path(value: str) -> Path | None:
    """Parse an absolute/UNC/``~`` path, or return None for an alias."""
    raw = str(value or "").strip().strip('"').strip("'")
    if not raw:
        return None
    expanded = os.path.expandvars(os.path.expanduser(raw))
    if (
        raw.startswith("~")
        or expanded.startswith(("\\\\", "//"))
        or (len(expanded) > 2 and expanded[1] == ":" and expanded[2] in "\\/")
        or os.path.isabs(expanded)
    ):
        return Path(expanded)
    return None
