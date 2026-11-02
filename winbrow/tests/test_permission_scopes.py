"""Permission scopes and exact one-shot grants, using a real, isolated manager."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from winbrow import permissions as perms
from winbrow.permissions import PermissionManager, action_key, permission_scope


@pytest.fixture
def pm(tmp_path, monkeypatch):
    monkeypatch.delenv("WINBROW_BYPASS_CONFIRM", raising=False)
    monkeypatch.delenv("WINBROW_AUTO_APPROVE_T2", raising=False)
    monkeypatch.setattr(perms, "_emit_confirm", Mock())
    return PermissionManager(path=tmp_path / "permissions.json")


def gate(pm, tool="app_install", args=None, **kwargs):
    return asyncio.run(
        pm.gate(tool, {"package": "Example.App"} if args is None else args, **kwargs)
    )


def request(pm, tool="app_install", args=None, **kwargs):
    allowed, reason, pending = gate(pm, tool, args, **kwargs)
    assert not allowed
    assert reason is None
    assert pending is not None
    return pending["confirmation_id"]


def approve(pm, tool="app_install", args=None, session_id="default", remember=False):
    cid = request(pm, tool, args, session_id=session_id)
    assert (
        pm.resolve_pending(cid, True, remember=remember, session_id=session_id)
        is not None
    )
    return cid


@pytest.mark.parametrize(
    "left,right",
    [
        ({"text": "x" * 160 + "A"}, {"text": "x" * 160 + "B"}),
        ({"text": "Hello"}, {"text": "hello"}),
        ({"Text": "hello"}, {"text": "hello"}),
        ({"text": " hello "}, {"text": "hello"}),
        ({"value": 1}, {"value": "1"}),
        ({"value": True}, {"value": "True"}),
        ({"nested": {"text": "A"}}, {"nested": {"text": "a"}}),
        ({"values": [1, 2]}, {"values": [2, 1]}),
    ],
)
def test_full_case_sensitive_action_keys(left, right):
    assert action_key("create_text_file", left) != action_key("create_text_file", right)


def test_canonical_action_key_is_stable():
    left = {"z": [{"b": 2, "a": "\u00e9"}], "a": None}
    right = {"a": None, "z": [{"a": "\u00e9", "b": 2}]}
    assert action_key("create_text_file", left) == action_key("create_text_file", right)
    assert action_key("Tool", left) != action_key("tool", left)
    assert action_key("Tool", left).startswith("v2:")


def test_unsafe_legacy_remembered_grants_are_not_migrated(pm):
    args = {"text": "Sensitive"}
    norm = {"text": "sensitive"}
    old_key = hashlib.sha256(
        f"create_text_file|{json.dumps(norm, sort_keys=True)}".encode("utf-8")
    ).hexdigest()[:32]
    pm.path.write_text(
        json.dumps({old_key: {"tier": "t2", "tool": "create_text_file"}})
    )
    reloaded = PermissionManager(path=pm.path)
    assert reloaded.list_allowed() == []
    request(reloaded, "create_text_file", args)


def test_scope_fills_empty_default_context_and_preserves_explicit_values(pm):
    with permission_scope("outer task", "outer-session"):
        cid = request(pm, utterance="", session_id="default")
        pending = pm.get_pending(cid)
        assert pending.utterance == "outer task"
        assert pending.session_id == "outer-session"
        explicit = request(
            pm,
            args={"package": "Other.App"},
            utterance="explicit task",
            session_id="explicit-session",
        )
        assert pm.get_pending(explicit) is None
        pending = pm.get_pending(explicit, session_id="explicit-session")
        assert pending.utterance == "explicit task"
        assert pending.session_id == "explicit-session"
    assert pm.get_pending(cid).session_id == "outer-session"
    cid = request(pm)
    assert pm.get_pending(cid).session_id == "default"
    assert pm.get_pending(cid).utterance == ""


def test_nested_scopes_inherit_session_and_restore_on_exception(pm):
    with permission_scope("outer", "session"):
        with pytest.raises(RuntimeError):
            with permission_scope("inner"):
                cid = request(pm)
                assert pm.get_pending(cid).session_id == "session"
                assert pm.get_pending(cid).utterance == "inner"
                raise RuntimeError("restore")
        cid = request(pm, args={"package": "Other.App"})
        assert pm.get_pending(cid).utterance == "outer"
        with permission_scope(session_id="default"):
            cid = request(pm)
            assert pm.get_pending(cid).session_id == "default"
    cid = request(pm, args={"package": "Third.App"})
    assert pm.get_pending(cid).session_id == "default"


def test_context_is_isolated_across_async_tasks(pm):
    async def worker(session):
        with permission_scope(session, session):
            await asyncio.sleep(0)
            allowed, _, pending = await pm.gate("app_install", {"package": "Same.App"})
            assert not allowed
            return pending

    async def run():
        return await asyncio.gather(worker("a"), worker("b"))

    first, second = asyncio.run(run())
    assert first["session_id"] == first["utterance"] == "a"
    assert second["session_id"] == second["utterance"] == "b"
    assert first["confirmation_id"] != second["confirmation_id"]


def test_pending_lookup_dedupes_only_in_same_session(pm):
    cid_a = request(pm, session_id="a")
    cid_b = request(pm, session_id="b")
    assert cid_a != cid_b
    assert request(pm, session_id="a") == cid_a
    assert pm.get_pending(cid_a, session_id="b") is None
    assert pm.resolve_pending(cid_a, True, remember=True, session_id="b") is None
    assert pm.get_pending(cid_a, session_id="a").status == "pending"
    assert [p["confirmation_id"] for p in pm.pending_list("a")] == [cid_a]
    assert len(pm.pending_list()) == 2
    cid_default = request(pm)
    key = action_key("app_install", {"package": "Example.App"})
    assert pm._find_any("other_install", key, "a") is None
    assert pm._find_pending("app_install", key, "b").id == cid_b
    with permission_scope(session_id="b"):
        assert pm.get_pending(cid_a) is None
        assert pm.resolve_pending(cid_a, True) is None
        assert pm._find_any("app_install", key).id == cid_b
        assert pm._find_any("app_install", key, "default").id == cid_default
        assert pm._find_pending("app_install", key, "default").id == cid_default
        assert pm.pending_list() == pm.pending_list("b")


@pytest.mark.parametrize("tool", ["app_install", "create_text_file"])
def test_legacy_approved_lookup_is_scoped_and_consumed_once(pm, tool):
    cid = approve(pm, tool, session_id="a")
    request(pm, tool, session_id="b")
    assert gate(pm, tool, session_id="a") == (True, None, None)
    assert pm.get_pending(cid) is None
    new_id = request(pm, tool, session_id="a")
    assert new_id != cid
    assert pm.list_allowed() == []


@pytest.mark.parametrize("tool", ["app_install", "create_text_file"])
@pytest.mark.parametrize("remember", [False, True])
def test_explicit_grants_are_exact_and_one_shot(pm, tool, remember):
    cid = approve(pm, tool, session_id="a", remember=remember)
    hook = Mock(return_value=True)
    pm.set_confirm_fn(hook)
    with permission_scope("resume", "a", cid):
        with permission_scope("nested resume"):
            assert gate(pm, tool) == (True, None, None)
        allowed, reason, pending = gate(pm, tool)
        assert not allowed and reason and pending is None
        assert pm.get_pending(cid) is None
    hook.assert_not_called()
    if tool == "app_install":
        assert pm.list_allowed() == []
        pm.set_confirm_fn(None)
        assert request(pm, tool, session_id="a") != cid
    elif remember:
        assert gate(PermissionManager(path=pm.path), tool)[0]
    else:
        assert pm.list_allowed() == []
        pm.set_confirm_fn(None)
        assert request(pm, tool, session_id="a") != cid


@pytest.mark.parametrize(
    "change", ["tool", "args-case", "args-tail", "session", "missing"]
)
def test_explicit_mismatch_cannot_use_hook_allowlist_or_another_approval(pm, change):
    tool = "create_text_file"
    args = {"text": "x" * 200 + "A"}
    cid = approve(pm, tool, args, session_id="a")
    other_tool = "notepad_save_as" if change == "tool" else tool
    other_args = {"text": "X" * 200 + "A"} if change == "args-case" else args
    if change == "args-tail":
        other_args = {"text": "x" * 200 + "B"}
    session = "b" if change == "session" else "a"
    # Both a matching remembered grant and a different approved ID must be ignored.
    pm.remember(action_key(other_tool, other_args), "t2", other_tool)
    other_id = None
    if change != "missing":
        with permission_scope(session_id=session):
            # Temporarily remove the allowlist to create an independent pending.
            allowed = pm._allowed.pop(action_key(other_tool, other_args))
            other_id = approve(pm, other_tool, other_args, session_id=session)
            pm._allowed[action_key(other_tool, other_args)] = allowed
    hook = Mock(return_value=True)
    pm.set_confirm_fn(hook)
    save = Mock(side_effect=AssertionError("must not save during an exact mismatch"))
    pm._save = save
    with permission_scope("resume", session, "missing" if change == "missing" else cid):
        allowed, reason, pending = gate(pm, other_tool, other_args)
        assert not allowed and reason and pending is None
    hook.assert_not_called()
    save.assert_not_called()
    assert pm.get_pending(cid).status == "approved"
    if other_id is not None:
        assert pm.get_pending(other_id).status == "approved"


def test_explicit_session_argument_is_not_overwritten_by_scope(pm):
    cid = approve(pm, session_id="explicit")
    with permission_scope("resume", "ambient", cid):
        assert gate(pm, session_id="explicit") == (True, None, None)


def test_pending_and_denied_exact_ids_do_not_authorize_or_call_hook(pm):
    cid = request(pm, "create_text_file", session_id="a")
    pm.remember(
        action_key("create_text_file", {"package": "Example.App"}),
        "t2",
        "create_text_file",
    )
    hook = Mock(return_value=True)
    pm.set_confirm_fn(hook)
    with permission_scope(session_id="a", confirmation_id=cid):
        allowed, reason, pending = gate(pm, "create_text_file")
        assert not allowed and reason is None
        assert pending["confirmation_id"] == cid
        assert pm.resolve_pending(cid, False) is not None
        allowed, reason, pending = gate(pm, "create_text_file")
        assert not allowed and reason == "denied by user" and pending is None
        assert pm.resolve_pending(cid, True, remember=True) is None
    hook.assert_not_called()


def test_legacy_denial_cannot_be_overridden_by_hook_or_remembered_grant(pm):
    cid = request(pm, "create_text_file")
    pm.resolve_pending(cid, False)
    pm.remember(
        action_key("create_text_file", {"package": "Example.App"}),
        "t2",
        "create_text_file",
    )
    hook = Mock(return_value=True)
    pm.set_confirm_fn(hook)
    assert gate(pm, "create_text_file") == (False, "denied by user", None)
    hook.assert_not_called()


def test_approved_pending_is_checked_before_interactive_confirmation(pm):
    cid = approve(pm)
    hook = Mock(return_value=False)
    pm.set_confirm_fn(hook)
    assert gate(pm) == (True, None, None)
    hook.assert_not_called()
    assert pm.get_pending(cid) is None
    assert gate(pm) == (False, "denied by user", None)
    hook.assert_called_once()


@pytest.mark.parametrize("tool", ["app_install", "create_text_file"])
@pytest.mark.parametrize("status", ["pending", "approved", "denied"])
@pytest.mark.parametrize(
    "api",
    ["get", "resolve", "find", "find-pending", "list", "consume", "consume-id", "gate"],
)
def test_expired_records_are_pruned_from_every_lookup(
    pm, monkeypatch, tool, status, api
):
    now = 1000.0
    monkeypatch.setattr(perms.time, "time", lambda: now)
    cid = request(pm, tool, session_id="a")
    if status != "pending":
        pm.resolve_pending(cid, status == "approved")
    now += perms.PENDING_TTL_S
    args = {"package": "Example.App"}
    key = action_key(tool, args)
    with permission_scope(session_id="a"):
        if api == "get":
            assert pm.get_pending(cid) is None
        elif api == "resolve":
            assert pm.resolve_pending(cid, True, remember=True) is None
        elif api == "find":
            assert pm._find_any(tool, key) is None
        elif api == "find-pending":
            assert pm._find_pending(tool, key) is None
        elif api == "list":
            assert pm.pending_list() == []
        elif api == "consume":
            pm.consume(tool, args)
        elif api == "consume-id":
            assert pm.consume_pending(cid) is None
        else:
            assert request(pm, tool) != cid
    assert cid not in pm._pending
    assert pm.list_allowed() == []
    assert not pm.path.exists()


def test_expired_explicit_id_fails_closed_even_with_remembered_grant(pm, monkeypatch):
    cid = approve(pm, "create_text_file", session_id="a", remember=True)
    created = pm.get_pending(cid).created
    monkeypatch.setattr(perms.time, "time", lambda: created + perms.PENDING_TTL_S)
    with permission_scope(session_id="a", confirmation_id=cid):
        allowed, reason, pending = gate(pm, "create_text_file")
        assert not allowed and reason and pending is None
    assert pm.get_pending(cid) is None


def test_exact_cleanup_never_removes_another_sessions_record(pm):
    cid_a = request(pm, session_id="a")
    cid_b = request(pm, session_id="b")
    assert pm.consume_pending(cid_a, session_id="b") is None
    assert pm.consume_pending(cid_a, session_id="a").id == cid_a
    assert pm.consume_pending(cid_a) is None
    assert pm.get_pending(cid_b) is not None
    with permission_scope(session_id="a"):
        assert pm.consume_pending(cid_b) is None
        pm.consume("app_install", {"package": "Example.App"})
    assert pm.get_pending(cid_b) is not None
    pm.consume("app_install", {"package": "Example.App"}, session_id="b")
    assert pm.get_pending(cid_b) is None


def test_legacy_cleanup_without_scope_retains_action_wide_behavior(pm):
    request(pm, session_id="a")
    request(pm, session_id="b")
    pm.consume("app_install", {"package": "Example.App"})
    assert pm.pending_list() == []


def test_resolve_is_idempotent_but_cannot_reverse_decision_or_add_remember(pm):
    cid = approve(pm, "create_text_file")
    pm._save = Mock(
        side_effect=AssertionError("repeated resolve must not persist a grant")
    )
    assert pm.resolve_pending(cid, True, remember=True).status == "approved"
    assert pm.resolve_pending(cid, False) is None
    assert pm.list_allowed() == []
    assert gate(pm, "create_text_file")[0]
    assert pm.resolve_pending(cid, True) is None
    pm._save.assert_not_called()


def test_pending_arguments_and_payloads_are_snapshots(pm):
    args = {"options": {"packages": ["Original.App"]}}
    cid = request(pm, args=args)
    args["options"]["packages"][0] = "Other.App"
    pending = pm.pending_list()[0]
    pending["args"]["options"]["packages"][0] = "Other.App"
    pm.resolve_pending(cid, True)
    with permission_scope(confirmation_id=cid):
        assert not gate(pm, args=args)[0]
        assert gate(pm, args={"options": {"packages": ["Original.App"]}})[0]


def test_same_approved_id_is_atomic_across_threads(pm):
    cid = approve(pm, session_id="a")
    barrier = Barrier(2)

    def attempt(_):
        with permission_scope(session_id="a", confirmation_id=cid):
            barrier.wait(timeout=5)
            return gate(pm)[0]

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(attempt, range(2))) == [False, True]
    assert pm.get_pending(cid) is None


@pytest.mark.parametrize("async_hook", [False, True])
def test_confirmation_hooks_still_work_and_t3_is_not_remembered(pm, async_hook):
    seen = []

    async def asynchronous(desc):
        await asyncio.sleep(0)
        seen.append(desc)
        return True

    def synchronous(desc):
        seen.append(desc)
        return True

    pm.set_confirm_fn(asynchronous if async_hook else synchronous)
    with permission_scope("install explicitly", "a"):
        assert gate(pm) == (True, None, None)
        assert gate(pm) == (True, None, None)
    assert len(seen) == 2
    assert seen[0]["utterance"] == "install explicitly"
    assert pm.list_allowed() == []
    assert not pm.path.exists()


def test_hook_exception_falls_back_to_pending(pm):
    pm.set_confirm_fn(Mock(side_effect=RuntimeError("no interactive channel")))
    assert request(pm)


def test_policy_block_still_precedes_explicit_grant(pm):
    with permission_scope(confirmation_id="missing"):
        allowed, reason, pending = gate(
            pm, "run_command", {"command": "Format-Volume -DriveLetter D"}
        )
        assert not allowed and "blocked by policy" in reason and pending is None


def test_explicit_scope_precedes_t2_auto_approval_without_saving(pm, monkeypatch):
    monkeypatch.setenv("WINBROW_AUTO_APPROVE_T2", "1")
    pm._save = Mock(side_effect=AssertionError("exact failure must not auto-remember"))
    with permission_scope(confirmation_id="missing"):
        allowed, reason, pending = gate(pm, "create_text_file")
        assert not allowed and reason and pending is None
    assert pm.list_allowed() == []
    pm._save.assert_not_called()


def test_invalid_permission_arguments_fail_closed(pm):
    allowed, reason, pending = gate(pm, "create_text_file", {"text": object()})
    assert not allowed and "invalid permission arguments" in reason and pending is None


def test_expiry_between_lookup_and_consumption_does_not_authorize(pm, monkeypatch):
    cid = approve(pm)
    expires_at = pm.get_pending(cid).created + perms.PENDING_TTL_S
    clock = Mock(side_effect=[expires_at - 1, expires_at - 1, expires_at])
    monkeypatch.setattr(perms.time, "time", clock)
    with permission_scope(confirmation_id=cid):
        allowed, reason, pending = gate(pm)
        assert not allowed and "expired" in reason and pending is None
    assert cid not in pm._pending


def test_exact_approval_cannot_authorize_a_changed_permission_tier(pm):
    tool = "custom_write"
    cid = approve(pm, tool, args={})
    with permission_scope(confirmation_id=cid):
        allowed, reason, pending = gate(pm, tool, {}, script="Stop-Service Spooler")
        assert not allowed and reason and pending is None
    assert pm.get_pending(cid).status == "approved"
    new_id = request(pm, tool, {}, script="Stop-Service Spooler")
    assert new_id != cid
    assert pm.get_pending(new_id).tier == "t3"


def test_explicit_scope_cannot_authorize_unrelated_auto_allowed_tools(pm):
    cid = approve(pm)
    with permission_scope(confirmation_id=cid):
        allowed, reason, pending = gate(pm, "current_time", {})
        assert not allowed and reason and pending is None
        assert gate(pm) == (True, None, None)


def test_wrong_session_cannot_resolve_or_persist_a_t2_grant(pm):
    cid = request(pm, "create_text_file", session_id="a")
    pm._save = Mock(side_effect=AssertionError("wrong session must not save"))
    with permission_scope(session_id="b"):
        assert pm.resolve_pending(cid, True, remember=True) is None
    assert pm.resolve_pending(cid, True, remember=True, session_id="b") is None
    assert pm.get_pending(cid).status == "pending"
    assert pm.list_allowed() == []
    pm._save.assert_not_called()
