"""Playbook skills and the bundled skill-script runner."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from winbrow.brain.agent_loop import AgentBrain
from winbrow.brain.model_gateway import GatewayResponse
from winbrow.brain.skill_registry import (
    SkillRegistryError,
    build_skills_metadata,
    load_skill_registry,
)
from winbrow.memory.store import MemoryStore
from winbrow import skill_scripts


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _playbook(name: str = "demo", category: str = "data-analysis") -> str:
    return f"""---
name: {name}
skill: playbook_{name}
kind: playbook
category: {category}
description: >
  Use when a test asks for the demo workflow. Do not use for anything else.
args: []
---

## When to Use

Test only.

## When Not to Use

Everywhere else.

## Step Pattern

1. Do the demo action.
"""


def test_playbook_parses_and_metadata_groups(tmp_path):
    _write(tmp_path / "demo" / "SKILL.md", _playbook())
    registry = load_skill_registry(str(tmp_path), sync_learned=False)

    meta = registry["playbook_demo"]
    assert meta.kind == "playbook"
    assert meta.category == "data-analysis"
    metadata = build_skills_metadata(registry)
    assert "playbook_demo" in metadata
    assert "DATA & ANALYSIS" in metadata
    assert "PLAYBOOK SKILLS" in metadata
    assert len(metadata) < 12000


def test_playbook_requires_prefixed_key(tmp_path):
    text = _playbook().replace("skill: playbook_demo", "skill: demo")
    _write(tmp_path / "demo" / "SKILL.md", text)

    try:
        load_skill_registry(str(tmp_path), sync_learned=False)
    except Exception as exc:  # load_skill_registry logs and skips
        assert "playbook_" in str(exc)
    else:
        # The loader skips malformed files; the registry must stay empty.
        assert load_skill_registry(str(tmp_path), sync_learned=False) == {}


def test_playbook_step_is_acknowledgement_only(tmp_path):
    _write(tmp_path / "demo" / "SKILL.md", _playbook())
    registry = load_skill_registry(str(tmp_path), sync_learned=False)

    brain = AgentBrain.__new__(AgentBrain)
    brain.skill_registry = registry
    result = asyncio.run(brain._run_step("playbook_demo", {}))

    assert result.success is True
    assert "Playbook loaded" in result.output
    assert "not task completion" in result.output


class _RecordingGateway:
    def __init__(self, plans):
        from types import SimpleNamespace

        self.providers = [SimpleNamespace(name="fake", model="fake-1")]
        self._plans = list(plans)
        self.seen: list[list[dict]] = []

    async def chat(self, messages, **kwargs):
        self.seen.append(messages)
        plan = self._plans.pop(0) if self._plans else {"kind": "done"}
        return GatewayResponse(
            content=json.dumps(plan), provider="fake", model="fake-1"
        )


class _EmptyRegistry:
    def get(self, name):
        # Unknown but executable singleton: validation only needs a record.
        return object()

    def available(self, ctx):
        return []

    def all_tools(self):
        return []


class _Ctx:
    def to_dict(self):
        return {"active_app": "Desktop", "running_apps": []}


class _Session:
    def context_block(self):
        return "none"


def test_playbook_detail_persists_across_later_tool_turns(tmp_path, monkeypatch):
    _write(tmp_path / "demo" / "SKILL.md", _playbook())
    monkeypatch.setenv("WINBROW_SKILLS_DIR", str(tmp_path))
    gateway = _RecordingGateway([
        {"kind": "action", "step": {"skill": "playbook_demo", "args": {}}},
        {"kind": "action", "step": {"skill": "run_command", "args": {"command": "x"}}},
        {"kind": "chat", "response": "ok"},
    ])
    store = MemoryStore(
        db_path=tmp_path / "memory.db",
        chroma_path=tmp_path / "chroma",
    )
    brain = AgentBrain(
        gateway, _EmptyRegistry(), store, executor=None,
        enable_skill_writer=False,
    )

    async def fake_run(skill, args, why="", ctx=None):
        from winbrow.brain.agent_loop import BrainStepResult

        return BrainStepResult(skill, args, True, "ok")

    brain._run_step = fake_run
    asyncio.run(brain.handle("do the demo", _Ctx(), _Session()))

    # Turn 2 saw the playbook body. Turn 3 (after run_command) must still see
    # it; otherwise the workflow instructions vanish mid-task.
    assert len(gateway.seen) >= 3
    second = gateway.seen[1][-1]["content"]
    third = gateway.seen[2][-1]["content"]
    assert "Do the demo action." in second
    assert "Do the demo action." in third
    assert "ACTIVE PLAYBOOK GUIDANCE" in third


def test_skill_script_runs_json_spec(tmp_path, monkeypatch):
    library = tmp_path / "library"
    _write(
        library / "demo" / "scripts" / "echo.py",
        "import argparse, json\n"
        "p=argparse.ArgumentParser(); p.add_argument('--spec-json', default='{}')\n"
        "a=p.parse_args(); s=json.loads(a.spec_json)\n"
        "print(json.dumps({'ok': True, 'message': 'hi ' + s.get('name',''), "
        "'data': s}))\n",
    )
    monkeypatch.setattr(skill_scripts, "_LIBRARY_ROOT", library)

    out = skill_scripts.execute_skill_script_tool(
        "run_skill_script",
        {"skill": "demo", "script": "echo.py", "spec": {"name": "world"}},
    )
    assert out["success"] is True
    assert out["output"] == "hi world"
    assert out["data"] == {"name": "world"}


def test_skill_script_rejects_traversal(tmp_path, monkeypatch):
    library = tmp_path / "library"
    library.mkdir(parents=True)
    monkeypatch.setattr(skill_scripts, "_LIBRARY_ROOT", library)

    out = skill_scripts.execute_skill_script_tool(
        "run_skill_script",
        {"skill": "..", "script": "escape.py", "spec": {}},
    )
    assert out["success"] is False
    assert "Invalid skill name" in out["output"]


def test_skill_script_rejects_bad_json(tmp_path, monkeypatch):
    library = tmp_path / "library"
    _write(library / "demo" / "scripts" / "echo.py", "print('{}')\n")
    monkeypatch.setattr(skill_scripts, "_LIBRARY_ROOT", library)

    out = skill_scripts.execute_skill_script_tool(
        "run_skill_script",
        {"skill": "demo", "script": "echo.py", "spec": "{not json"},
    )
    assert out["success"] is False
    assert "valid JSON" in out["output"]
