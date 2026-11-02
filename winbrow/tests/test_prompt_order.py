"""Prompt layout: HISTORY early, volatile text after the stable prefix."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from winbrow.brain.prompt import build_loop_messages


def _content(**overrides):
    args = {
        "utterance": "do the thing",
        "history_block": "Step 1: web_fetch",
        "context_block": "ctx",
        "memory_block": "memory",
        "skills_block": "",
        "tried_block": "ALREADY TRIED:",
        "steps_remaining": 7,
        "skill_detail": "detail",
        "volatile_block": "PLANNER FEEDBACK: look again",
    }
    args.update(overrides)
    return build_loop_messages(**args)[1]["content"]


def test_history_before_context_and_volatile_tail():
    content = _content()
    positions = [
        content.index("GOAL: do the thing"),
        content.index("HISTORY:"),
        content.index("ALREADY TRIED:"),
        content.index("WINDOWS CONTEXT:"),
        content.index("CONVERSATION:"),
        content.index("PLANNER FEEDBACK:"),
        content.index("STEPS REMAINING: 7"),
        content.index("GOAL (restated):"),
        content.index("SKILL DETAIL"),
        content.index("What is the best next action or bounded known-input batch?"),
    ]
    assert positions == sorted(positions)


def test_tried_block_is_after_history():
    content = _content()
    assert content.index("HISTORY:") < content.index("ALREADY TRIED:")


def test_legacy_planner_message_also_puts_history_before_steps():
    from winbrow.brain.prompt import build_planner_message
    message = build_planner_message("goal", [], 7)
    assert message.index("HISTORY:") < message.index("STEPS REMAINING: 7")


def test_windows_context_names_the_real_user_folders():
    from winbrow.brain.agent_loop import _ctx_block

    class _Ctx:
        def to_dict(self):
            return {"active_app": "Desktop", "running_apps": []}

    block = _ctx_block(_Ctx())
    assert "USER FOLDERS" in block
    assert str(Path.home() / "Desktop") in block
    assert "Never save it inside the WinBrow app/project folder" in block


def test_static_prompt_has_an_output_location_rule():
    from winbrow.brain.prompt import SYSTEM_PROMPT_STATIC

    assert "OUTPUT LOCATION" in SYSTEM_PROMPT_STATIC
    assert "USER FOLDERS" in SYSTEM_PROMPT_STATIC
    assert "NEVER save a deliverable inside the WinBrow app/project" in (
        SYSTEM_PROMPT_STATIC
    )


def test_static_prompt_routes_pdf_export_to_the_skill_helper():
    from winbrow.brain.prompt import SYSTEM_PROMPT_STATIC

    assert "NEVER export a PDF by calling run_command" in SYSTEM_PROMPT_STATIC
    assert "render_deck.py" in SYSTEM_PROMPT_STATIC
    assert "pdf_tool.py" in SYSTEM_PROMPT_STATIC
    assert "--print-to-pdf" in SYSTEM_PROMPT_STATIC
