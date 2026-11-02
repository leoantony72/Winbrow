"""find_files uses only Everything (es.exe) for files and folders."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from winbrow.registry import ToolRegistry


def test_find_files_uses_everything_cli():
    tool = ToolRegistry().get("find_files")
    assert tool is not None
    script = tool.script
    assert "es.exe" in script
    assert "-instance" in script
    assert "-timeout 5000" in script
    assert "WinBrow\\Everything\\es.exe" in script


def test_find_files_is_case_insensitive():
    tool = ToolRegistry().get("find_files")
    script = tool.script
    # ES's -i means "match case", which would hide KAITHI_2019 for "kaithi".
    assert "-i $term" not in script
    assert "-n $limit -i" not in script


def test_find_files_returns_folders_as_well_as_files():
    tool = ToolRegistry().get("find_files")
    script = tool.script
    assert "/ad" in script
    assert "/a-d" in script
    assert "IsDir" in script
    assert "[folder]" in script
    # Directories are real entries in the index; do not filter them out.
    assert "-PathType Leaf" not in script


def test_find_files_reads_paths_as_utf8():
    tool = ToolRegistry().get("find_files")
    script = tool.script
    # Native stdout decoding in the persistent host mangles non-ASCII paths
    # (e.g. the NBSP in KAITHI_2019_Tamil Proper...), so use ES JSON export.
    assert "-export-json" in script
    assert "-utf8-bom" in script
    assert "[System.Text.Encoding]::UTF8" in script
    assert "ConvertFrom-Json" in script


def test_find_files_has_no_other_search_backend():
    tool = ToolRegistry().get("find_files")
    script = tool.script
    assert "SYSTEMINDEX" not in script
    assert "Search.CollatorDSO" not in script
    assert "Get-ChildItem" not in script
    assert "Windows Search" not in script
    assert "Downloads" not in script
    assert "Pictures" not in script


def test_find_files_starts_portable_everything_when_stopped():
    tool = ToolRegistry().get("find_files")
    script = tool.script
    assert "Everything.exe" in script
    assert "Start-Process -FilePath $exe" in script
    assert "-get-everything-version" in script
    assert "if ($results.Count -gt 0)" in script
    assert "elseif ($results.Count -gt 0)" in script
    assert "$noTerm" in script
    assert "$term = '{{search_term}}'" in script
