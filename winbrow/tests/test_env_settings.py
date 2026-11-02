"""In-app .env settings: masking, merging, and live os.environ updates."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from winbrow.env_settings import (
    _catalog_fields,
    describe_env,
    parse_env_file,
    save_env,
)


def test_parse_env_skips_comments_and_unquotes(tmp_path: Path):
    path = tmp_path / ".env"
    path.write_text(
        "# comment\nA=1\n# B=2\nC=\"hello world\"\nD='single'\n\n",
        encoding="utf-8",
    )
    assert parse_env_file(path) == {"A": "1", "C": "hello world", "D": "single"}


def test_describe_masks_secret_values(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    path = tmp_path / ".env"
    path.write_text(
        "NEBIUS_API_KEY=secret-value\nWINBROW_MAX_STEPS=42\n",
        encoding="utf-8",
    )
    data = describe_env(path)
    brain = next(group for group in data["groups"] if group["id"] == "brain")
    key = next(field for field in brain["fields"] if field["key"] == "NEBIUS_API_KEY")
    assert key["secret"] is True
    assert key["value"] == ""
    assert key["is_set"] is True
    assert "secret-value" not in str(data)

    agent = next(group for group in data["groups"] if group["id"] == "agent")
    steps = next(field for field in agent["fields"] if field["key"] == "WINBROW_MAX_STEPS")
    assert steps["value"] == "42"
    assert steps["default"] == "20"
    assert steps["source"] == "env"


def test_describe_shows_defaults_for_unset_fields(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("WINBROW_MAX_STEPS", raising=False)
    path = tmp_path / ".env"
    path.write_text("EXISTING=old\n", encoding="utf-8")
    data = describe_env(path)
    agent = next(group for group in data["groups"] if group["id"] == "agent")
    steps = next(field for field in agent["fields"] if field["key"] == "WINBROW_MAX_STEPS")
    assert steps["value"] == "20"
    assert steps["default"] == "20"
    assert steps["source"] == "default"
    assert steps["in_file"] is False

    brain = next(group for group in data["groups"] if group["id"] == "brain")
    provider = next(
        field for field in brain["fields"] if field["key"] == "WINBROW_BRAIN_PROVIDER"
    )
    assert provider["value"] == "auto"
    assert provider["source"] == "default"


def test_token_budget_fields_are_not_secrets(tmp_path: Path, monkeypatch):
    for key in (
        "WINBROW_CONTEXT_TOKENS",
        "WINBROW_REASONING_MAX_TOKENS",
        "WINBROW_PLANNER_MAX_TOKENS",
    ):
        monkeypatch.delenv(key, raising=False)
    data = describe_env(tmp_path / ".env")
    fields = {
        field["key"]: field
        for group in data["groups"]
        for field in group["fields"]
    }
    for key, value in (
        ("WINBROW_CONTEXT_TOKENS", "0"),
        ("WINBROW_REASONING_MAX_TOKENS", "2000"),
        ("WINBROW_PLANNER_MAX_TOKENS", "16000"),
    ):
        field = fields[key]
        assert field["secret"] is False
        assert field["value"] == value
        assert field["default"] == value

    assert fields["NEBIUS_API_KEY"]["secret"] is True
    assert fields["NEBIUS_API_KEY"]["value"] == ""


def test_save_env_merges_preserves_comments_and_applies(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("WINBROW_TEST_SETTING", raising=False)
    path = tmp_path / ".env"
    path.write_text(
        "# keep me\nEXISTING=old\nWINBROW_MAX_STEPS=10\n",
        encoding="utf-8",
    )
    result = save_env(
        {
            "WINBROW_MAX_STEPS": "25",
            "WINBROW_TEST_SETTING": "hello world",
        },
        path=path,
    )
    assert result["status"] == "saved"
    assert "WINBROW_MAX_STEPS" in result["saved"]
    assert os.environ["WINBROW_MAX_STEPS"] == "25"
    assert os.environ["WINBROW_TEST_SETTING"] == "hello world"
    values = parse_env_file(path)
    assert values["EXISTING"] == "old"
    assert values["WINBROW_MAX_STEPS"] == "25"
    assert values["WINBROW_TEST_SETTING"] == "hello world"
    text = path.read_text(encoding="utf-8")
    assert "# keep me" in text
    monkeypatch.delenv("WINBROW_TEST_SETTING", raising=False)


def test_save_env_unset_removes_key(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("WINBROW_TEST_OLD", "1")
    path = tmp_path / ".env"
    path.write_text("WINBROW_TEST_OLD=1\nKEEP=yes\n", encoding="utf-8")
    result = save_env({}, unset=["WINBROW_TEST_OLD"], path=path)
    assert result["unset"] == ["WINBROW_TEST_OLD"]
    assert "WINBROW_TEST_OLD" not in parse_env_file(path)
    assert "WINBROW_TEST_OLD" not in os.environ
    assert parse_env_file(path)["KEEP"] == "yes"


def test_save_env_rejects_invalid_names(tmp_path: Path):
    try:
        save_env({"BAD-NAME": "x"}, path=tmp_path / ".env")
    except ValueError as exc:
        assert "Invalid environment variable" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_save_env_marks_restart_fields(tmp_path: Path):
    result = save_env({"WINBROW_VOICE": "1"}, path=tmp_path / ".env")
    assert result["requires_restart"] is True
    assert result["restart_keys"] == ["WINBROW_VOICE"]
    os.environ.pop("WINBROW_VOICE", None)


def test_catalog_covers_every_env_example_key():
    pattern = re.compile(
        r"^\s*#?\s*([A-Za-z_][A-Za-z0-9_]*)\s*=",
        re.MULTILINE,
    )
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    keys = set(pattern.findall(text))
    assert keys
    missing = keys - set(_catalog_fields())
    assert not missing, f".env.example keys missing from Settings: {sorted(missing)}"
