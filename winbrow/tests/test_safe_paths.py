"""Write-path policy: any user folder is allowed, Windows-owned trees are not."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from winbrow import files, image_tools
from winbrow.brain.batching import validate_steps
from winbrow.registry import ToolRegistry
from winbrow.safe_paths import (
    is_protected_path,
    project_root,
    remap_project_user_folder,
    write_refusal,
)


def _system_root() -> Path:
    return Path(os.environ.get("SystemRoot") or r"C:\Windows")


def test_system_trees_are_protected():
    root = _system_root()
    assert is_protected_path(root)
    assert is_protected_path(root / "System32" / "drivers" / "x.sys")
    program_files = os.environ.get("ProgramFiles")
    if program_files:
        assert is_protected_path(Path(program_files) / "app" / "x.dll")
    assert write_refusal(root) != ""


def test_user_and_other_drives_are_allowed(tmp_path):
    assert not is_protected_path(tmp_path)
    assert not is_protected_path(tmp_path / "deck" / "index.html")
    assert write_refusal(tmp_path) == ""
    if Path("D:/").exists():
        assert not is_protected_path(Path("D:/projects/deck"))


def test_folder_aliases_and_absolute_paths(tmp_path):
    home = Path(files.user_home())
    assert files.resolve_user_folder("Desktop") == home / "Desktop"
    assert files.resolve_user_folder("desktop/reports") == home / "Desktop" / "reports"
    assert files.resolve_user_folder("deck") == home / "Desktop" / "deck"
    assert files.resolve_user_folder(str(tmp_path / "deck")) == tmp_path / "deck"


def test_project_local_desktop_is_remapped_to_the_real_user_desktop():
    home = Path(files.user_home())
    accidental = project_root() / "Desktop" / "thrissur-pooram"
    assert (
        remap_project_user_folder(accidental)
        == home / "Desktop" / "thrissur-pooram"
    )
    assert (
        files.resolve_user_folder(str(accidental))
        == home / "Desktop" / "thrissur-pooram"
    )


def test_ordinary_project_paths_are_not_remapped():
    internal = project_root() / "src" / "module.py"
    assert remap_project_user_folder(internal) == internal


def test_skill_script_relative_desktop_is_not_the_project_folder():
    from winbrow.skill_script_utils import resolve_path

    home = Path(files.user_home())
    expected = (home / "Desktop" / "deck").resolve()
    assert resolve_path("Desktop\\deck") == expected
    assert resolve_path(project_root() / "Desktop" / "deck") == expected


def test_write_named_text_file_accepts_an_absolute_folder(tmp_path):
    target = tmp_path / "deck" / "assets"
    result = files.write_named_text_file({
        "filename": "notes.txt",
        "content": "hello",
        "folder": str(target),
    })
    assert result["success"] is True
    assert (target / "notes.txt").read_text(encoding="utf-8") == "hello"


def test_write_named_text_file_accepts_an_absolute_filename(tmp_path):
    target = tmp_path / "deck" / "index.html"
    result = files.write_named_text_file({
        "filename": str(target),
        "content": "<h1>x</h1>",
    })
    assert result["success"] is True
    assert target.read_text(encoding="utf-8") == "<h1>x</h1>"


def test_write_named_text_file_refuses_system_folder(tmp_path):
    result = files.write_named_text_file({
        "filename": "x.txt",
        "content": "no",
        "folder": str(_system_root()),
    })
    assert result["success"] is False
    assert "Refusing" in result["output"]


def test_download_images_folder_accepts_an_absolute_path(tmp_path):
    registry = ToolRegistry()
    for tool in image_tools.get_image_tools():
        registry.register(tool)
    result = validate_steps(
        {
            "step": {
                "skill": "download_images",
                "args": {"query": "cat", "folder": str(tmp_path / "deck")},
            }
        },
        registry,
        1,
    )
    assert result[0]["args"]["folder"] == str(tmp_path / "deck")


def test_download_images_resolver_refuses_system_folder():
    with pytest.raises(image_tools.ImageToolError):
        image_tools.resolve_folder(str(_system_root() / "Temp"))
