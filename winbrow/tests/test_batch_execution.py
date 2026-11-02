"""Batch guard, exact permission continuation and shared-execution wiring."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from winbrow import permissions as perms
from winbrow.agent import WinBrowAgent
from winbrow.brain.agent_loop import BrainResult
from winbrow.brain.model_gateway import GatewayResponse
from winbrow.execution import ExecutionOwnership
from winbrow.permissions import PermissionManager
from winbrow.registry import ArgSpec, Tool


def _tool(name, impl=None, args=()):
    return Tool(
        name=name,
        description="test",
        script="",
        impl=impl,
        args=[ArgSpec(arg, "text", "", default="") for arg in args],
    )


def _agent(tools, browser=None):
    agent = WinBrowAgent.__new__(WinBrowAgent)
    agent.registry = {tool.name: tool for tool in tools}
    agent.browser = browser
    return agent


class _BrainGateway:
    """Scripted planner gateway for executor-loop tests."""

    def __init__(self, plans):
        self.providers = [SimpleNamespace(name="fake", model="fake-1")]
        self._plans = list(plans)

    async def chat(self, messages, **kwargs):
        plan = self._plans.pop(0) if self._plans else {"kind": "done"}
        return GatewayResponse(
            content=json.dumps(plan), provider="fake", model="fake-1"
        )


class _BrainSession:
    def context_block(self):
        return "none"


def _signature(**changes):
    return {
        "exists": True,
        "count": 1,
        "tag": "input",
        "type": "text",
        "id": "field",
        "name": "field",
        "role": "",
        "href": "",
        "label": "Email",
        "disabled": False,
        "connected": True,
        "visible": True,
        **changes,
    }


def _snapshot(targets=None, **identity):
    return {
        "success": True,
        "identity": {
            "tab_id": "agent-tab",
            "url": "https://example.test/form",
            "document_id": "document-token",
            **identity,
        },
        "targets": {"#email": _signature()} if targets is None else targets,
    }


class FakeBrowser:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def batch_state(self, selectors=None):
        self.calls.append(list(selectors or []))
        return self.responses.pop(0)


BROWSER_BATCH = [
    {"skill": "browser_interact", "args": {"instruction": "fill", "selector": "#email"}},
    {"skill": "browser_read_full", "args": {}},
]


def test_browser_guard_captures_identity_and_remaining_targets():
    browser = FakeBrowser([_snapshot(), _snapshot()])
    agent = _agent(
        [_tool("browser_interact", "browser"), _tool("browser_read_full", "browser")],
        browser,
    )
    first = asyncio.run(agent._guard_batch(BROWSER_BATCH, None))
    assert first["success"] is True
    assert first["state"]["identity"]["document_id"] == "document-token"
    assert browser.calls == [["#email"]]

    second = asyncio.run(
        agent._guard_batch(BROWSER_BATCH[1:], first["state"], "browser_interact")
    )
    assert second["success"] is True
    assert second["state"]["targets"]["#email"] == _signature()


@pytest.mark.parametrize(
    "snapshot, expected",
    [
        (_snapshot(document_id="reloaded"), "navigated or reloaded"),
        (_snapshot(targets={"#email": _signature(label="Changed")}), "changed"),
        (_snapshot(targets={}), "changed"),
    ],
)
def test_browser_guard_stops_on_changed_document_or_target(snapshot, expected):
    agent = _agent(
        [_tool("browser_interact", "browser"), _tool("browser_read_full", "browser")],
        FakeBrowser([snapshot]),
    )
    state = {
        "identity": _snapshot()["identity"],
        "targets": _snapshot()["targets"],
    }
    result = asyncio.run(agent._guard_batch(BROWSER_BATCH, state))
    assert result["success"] is False
    assert expected in result["output"]


@pytest.mark.parametrize(
    "target, expected",
    [
        (_signature(exists=False, count=0), "no longer on the page"),
        (_signature(count=2), "ambiguous"),
        (_signature(visible=False), "not visible"),
        (_signature(disabled=True), "disabled"),
    ],
)
def test_browser_guard_requires_one_actionable_observed_target(target, expected):
    agent = _agent(
        [_tool("browser_interact", "browser")],
        FakeBrowser([_snapshot(targets={"#email": target})]),
    )
    result = asyncio.run(agent._guard_batch(BROWSER_BATCH[:1], None))
    assert result["success"] is False
    assert expected in result["output"]


def test_browser_guard_fails_closed_when_state_cannot_be_captured():
    agent = _agent(
        [_tool("browser_interact", "browser")],
        FakeBrowser(
            [
                {
                    "success": False,
                    "error": "No remembered agent tab",
                    "identity": {"tab_id": None, "url": None, "document_id": None},
                    "targets": {},
                }
            ]
        ),
    )
    result = asyncio.run(agent._guard_batch(BROWSER_BATCH[:1], None))
    assert result["success"] is False
    assert "No remembered agent tab" in result["output"]


def test_desktop_batches_require_a_reviewed_window_guard():
    browser = FakeBrowser([])
    agent = _agent(
        [
            _tool("computer_click", "computer"),
            _tool("focus_window", "computer"),
        ],
        browser,
    )
    result = asyncio.run(
        agent._guard_batch(
            [
                {"skill": "computer_click", "args": {"x": 1, "y": 2}},
                {"skill": "focus_window", "args": {"title": "Notepad"}},
            ],
            None,
        )
    )
    assert result["success"] is False
    assert "single actions" in result["output"]
    assert browser.calls == []


def test_desktop_batch_replans_as_singletons_without_running_members():
    from winbrow.brain.agent_loop import AgentBrain
    from winbrow.memory.store import MemoryStore

    agent = _agent(
        [_tool("focus_window", "computer"), _tool("computer_type", "computer")],
        FakeBrowser([]),
    )
    executed = []

    async def executor(skill, args):
        executed.append(skill)
        return {"success": True, "output": "ok"}

    brain = AgentBrain(
        _BrainGateway(
            [
                {
                    "kind": "action",
                    "steps": [
                        {"skill": "focus_window", "args": {"title": "Notepad"}},
                        {"skill": "computer_type", "args": {"text": "known"}},
                    ],
                },
                {
                    "kind": "action",
                    "steps": [{"skill": "focus_window", "args": {"title": "Notepad"}}],
                },
                {"kind": "done", "summary": "focused"},
            ]
        ),
        agent.registry,
        MemoryStore(db_path=Path(tempfile.gettempdir()) / "wb_batch_guard.db"),
        executor,
        batch_guard=agent._guard_batch,
    )

    ctx = SimpleNamespace(to_dict=lambda: {})
    result = asyncio.run(brain.handle("focus and type", ctx, _BrainSession()))

    assert result.success is True
    assert executed == ["focus_window"]
    assert result.batches[0]["attempted"] == 0
    assert "single actions" in result.batches[0]["stop_reason"]


def test_ui_batch_without_a_guard_stops_after_one_replan():
    from winbrow.brain.agent_loop import AgentBrain
    from winbrow.memory.store import MemoryStore

    batch = {
        "kind": "action",
        "steps": [
            {"skill": "browser_read_full", "args": {}},
            {"skill": "browser_read_full", "args": {}},
        ],
    }

    brain = AgentBrain(
        _BrainGateway([batch, batch]),
        {"browser_read_full": _tool("browser_read_full", "browser")},
        MemoryStore(db_path=Path(tempfile.gettempdir()) / "wb_batch_noguard.db"),
        executor=None,
    )

    result = asyncio.run(
        brain.handle(
            "read twice", SimpleNamespace(to_dict=lambda: {}), _BrainSession()
        )
    )

    assert result.success is False
    assert result.steps == []
    assert "resource-state guard" in result.response


def test_batch_step_events_report_identity_and_ordinal():
    from winbrow.brain.agent_loop import AgentBrain
    from winbrow.memory.store import MemoryStore

    agent = _agent(
        [
            _tool("create_text_file", None, ("filename", "content")),
            _tool("read_document", "document", ("path",)),
        ],
        FakeBrowser([]),
    )

    async def executor(skill, args):
        return {"success": True, "output": f"ran {skill}"}

    brain = AgentBrain(
        _BrainGateway(
            [
                {
                    "kind": "action",
                    "steps": [
                        {
                            "skill": "create_text_file",
                            "args": {"filename": "a.txt", "content": "known"},
                        },
                        {"skill": "read_document", "args": {"path": "a.txt"}},
                    ],
                },
                {"kind": "done", "summary": "done"},
            ]
        ),
        agent.registry,
        MemoryStore(db_path=Path(tempfile.gettempdir()) / "wb_batch_events.db"),
        executor,
    )
    events = []

    async def emit(event):
        events.append(event)

    result = asyncio.run(
        brain.handle(
            "create and read", SimpleNamespace(to_dict=lambda: {}), _BrainSession(),
            emit=emit,
        )
    )

    steps = [event for event in events if event.get("type") == "brain_step"]
    assert [event["batch_index"] for event in steps] == [1, 2]
    assert [event["index"] for event in steps] == [1, 2]
    assert {event["batch_id"] for event in steps} == {
        result.batches[0]["batch_id"]
    }
    assert all(event["batch_size"] == 2 for event in steps)
    assert result.batches[0]["attempted"] == 2
    assert result.batches[0]["unexecuted"] == []


def test_non_ui_batches_keep_their_state_without_touching_the_browser():
    browser = FakeBrowser([])
    agent = _agent(
        [_tool("web_fetch", "web"), _tool("read_document", "document")],
        browser,
    )
    result = asyncio.run(
        agent._guard_batch(
            [
                {"skill": "web_fetch", "args": {"url": "https://example.test"}},
                {"skill": "read_document", "args": {"path": "notes.txt"}},
            ],
            {"marker": 1},
        )
    )
    assert result == {"success": True, "state": {"marker": 1}, "output": ""}
    assert browser.calls == []


@pytest.fixture
def pm(tmp_path, monkeypatch):
    monkeypatch.setattr(perms, "_emit_confirm", Mock())
    manager = PermissionManager(path=tmp_path / "permissions.json")
    monkeypatch.setattr(perms, "get_permissions", lambda: manager)
    return manager


def _pending(manager, session_id="s1", package="Example.App"):
    allowed, reason, pending = asyncio.run(
        manager.gate(
            "app_install",
            {"package": package},
            utterance="install the app",
            session_id=session_id,
        )
    )
    assert not allowed and reason is None and pending
    return pending["confirmation_id"]


def _confirm_agent():
    agent = WinBrowAgent.__new__(WinBrowAgent)
    agent.history = []
    agent.execution = ExecutionOwnership()
    agent.session = SimpleNamespace(record_turn=Mock())
    agent.store = SimpleNamespace(record_command=Mock())
    agent._trace_brain_run = Mock()
    agent.brain = SimpleNamespace(
        has_continuation=Mock(return_value=True),
        resume_pending=AsyncMock(
            return_value=BrainResult(
                "action", success=True, response="resumed", run_id="run-1"
            )
        ),
        discard_continuation=Mock(),
    )
    agent.execute = AsyncMock(side_effect=AssertionError("must not replay the goal"))
    return agent


def test_exact_approval_resumes_only_the_queued_suffix(pm):
    cid = _pending(pm, session_id="default")
    agent = _confirm_agent()

    result = asyncio.run(agent.confirm_pending(cid, True, session_id="default"))

    assert result["route"]["tier"] == "permission_resume"
    assert result["execution"]["output"] == "resumed"
    agent.brain.resume_pending.assert_awaited_once_with(
        cid, "default", emit=None
    )
    agent.execute.assert_not_awaited()
    assert pm.get_pending(cid).status == "approved"
    assert agent.history[-1] is result
    agent.session.record_turn.assert_called_once()
    agent.store.record_command.assert_called_once()


def test_approval_resume_reacquires_the_shared_state_lease(pm):
    cid = _pending(pm, session_id="default")
    agent = _confirm_agent()

    async def main():
        order = []
        entered = asyncio.Event()
        release = asyncio.Event()

        async def first():
            async with agent.execution.hold():
                entered.set()
                await release.wait()
                order.append("first-out")

        async def resume():
            await entered.wait()
            result = await agent.confirm_pending(cid, True, session_id="default")
            order.append("resume")
            return result

        one = asyncio.create_task(first())
        two = asyncio.create_task(resume())
        await asyncio.sleep(0.05)
        assert order == []  # approval cannot interleave with the running goal
        release.set()
        await one
        return await two, order

    result, order = asyncio.run(main())
    assert result["route"]["tier"] == "permission_resume"
    assert order == ["first-out", "resume"]


def test_denial_discards_the_cursor_and_consumes_the_exact_record(pm):
    cid = _pending(pm)
    agent = _confirm_agent()

    result = asyncio.run(agent.confirm_pending(cid, False, session_id="s1"))

    assert result["execution"]["type"] == "denied"
    agent.brain.discard_continuation.assert_called_once_with(cid)
    agent.brain.resume_pending.assert_not_awaited()
    agent.execute.assert_not_awaited()
    assert pm.get_pending(cid) is None


def test_unknown_or_wrong_session_confirmation_fails_closed(pm):
    cid = _pending(pm, session_id="s1")
    agent = _confirm_agent()

    assert asyncio.run(agent.confirm_pending("missing", True, session_id="s1")) is None
    assert asyncio.run(agent.confirm_pending(cid, True, session_id="other")) is None
    agent.brain.resume_pending.assert_not_awaited()
    agent.execute.assert_not_awaited()
    assert pm.get_pending(cid).status == "pending"


def test_chat_yes_uses_exact_continuation(pm, monkeypatch):
    cid = _pending(pm, session_id="default")
    agent = _confirm_agent()
    agent.gateway = SimpleNamespace(available=False)
    agent.execution = ExecutionOwnership()
    agent._last_focus_failure = None
    agent._last_focus_target = None
    agent.confirm_pending = AsyncMock(return_value={"resumed": cid})
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = asyncio.run(
        WinBrowAgent.execute(agent, "yes", session_id="default")
    )

    assert result == {"resumed": cid}
    agent.confirm_pending.assert_awaited_once()
    assert agent.confirm_pending.await_args.args[0] == cid


def test_execution_lease_is_reentrant_and_inherited_by_children():
    async def main():
        ownership = ExecutionOwnership()
        async with ownership.hold():
            async with ownership.hold():
                pass

            async def child():
                async with ownership.hold():
                    return "child"

            return await asyncio.create_task(child())

    assert asyncio.run(main()) == "child"


def test_unrelated_goals_do_not_interleave_shared_state():
    async def main():
        ownership = ExecutionOwnership()
        order = []
        release = asyncio.Event()

        async def first():
            async with ownership.hold():
                order.append("first-in")
                await release.wait()
                order.append("first-out")

        async def second():
            async with ownership.hold():
                order.append("second-in")

        one = asyncio.create_task(first())
        await asyncio.sleep(0)
        two = asyncio.create_task(second())
        await asyncio.sleep(0)
        assert order == ["first-in"]
        release.set()
        await asyncio.gather(one, two)
        return order

    assert asyncio.run(main()) == ["first-in", "first-out", "second-in"]
