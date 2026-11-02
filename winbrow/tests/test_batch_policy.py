"""Pure policy/preflight and prompt tests: no live browser, desktop or executor."""

from __future__ import annotations

import copy
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from winbrow.brain.batching import (
    BatchPolicy,
    max_actions_per_turn,
    policy_for,
    validate_steps,
)
from winbrow.brain.prompt import (
    BROWSER_BREVITY,
    PLANNER_JSON_SCHEMA,
    SYSTEM_PROMPT_STATIC,
    build_loop_messages,
    build_planner_message,
)
from winbrow.registry import ArgSpec, Tool


def tool(name, impl=None, args=(), **kwargs):
    return Tool(
        name=name, description="test", script="", impl=impl, args=list(args), **kwargs
    )


def step(name, **args):
    return {"skill": name, "args": args}


def plan(*steps):
    return {"kind": "action", "steps": list(steps)}


@pytest.fixture(autouse=True)
def default_cap(monkeypatch):
    monkeypatch.delenv("WINBROW_MAX_ACTIONS_PER_TURN", raising=False)


@pytest.fixture
def registry():
    from winbrow.browser_tools import get_browser_tools
    from winbrow.computer.tools import get_computer_tools
    from winbrow.document_tools import get_document_tools
    from winbrow.installer import get_installer_tools
    from winbrow.web_tools import get_web_tools

    records = (
        get_browser_tools()
        + get_computer_tools()
        + get_document_tools()
        + get_web_tools()
        + get_installer_tools()
    )
    records += [
        tool(
            "create_text_file",
            args=[ArgSpec("filename", "text", ""), ArgSpec("content", "text", "")],
        ),
        tool("current_time"),
        tool("find_files", args=[ArgSpec("pattern", "text", "", default="*")]),
        tool("notepad_open", "adapter"),
        tool(
            "office_save_as_pdf",
            "adapter",
            [ArgSpec("path", "text", ""), ArgSpec("out_path", "text", "")],
        ),
        tool("paint_invert_colors", "adapter"),
        tool("vscode_run_command", "adapter"),
        tool("run_command", "shell"),
        tool("run_skill_script", "skill_scripts"),
        tool("mcp_filesystem_write_file", "mcp"),
        tool("learned_action", is_learned=True),
    ]
    return {record.name: record for record in records}


@pytest.mark.parametrize(
    "value, expected",
    [
        (None, 5),
        ("", 5),
        ("oops", 5),
        ("2.5", 5),
        ("true", 5),
        ("NaN", 5),
        ("0", 1),
        ("-9", 1),
        ("1", 1),
        ("5", 5),
        ("10", 10),
        ("99", 10),
        (" 3 ", 3),
    ],
)
def test_environment_cap(monkeypatch, value, expected):
    if value is not None:
        monkeypatch.setenv("WINBROW_MAX_ACTIONS_PER_TURN", value)
    assert max_actions_per_turn() == expected


def test_cap_is_read_after_import(monkeypatch):
    assert max_actions_per_turn() == 5
    monkeypatch.setenv("WINBROW_MAX_ACTIONS_PER_TURN", "2")
    assert max_actions_per_turn() == 2


def test_policy_is_immutable():
    policy = BatchPolicy(True, False, False, "desktop", "reviewed")
    with pytest.raises(FrozenInstanceError):
        policy.__setattr__("parallel", True)


@pytest.mark.parametrize(
    "name, resource, parallel",
    [
        ("web_search", "web", True),
        ("web_fetch", "web", True),
        ("read_document", "filesystem", True),
        ("find_files", "filesystem", True),
        ("current_time", "clock", True),
        ("browser_read_full", "browser", False),
        ("focus_window", "desktop", False),
        ("computer_type", "desktop", False),
        ("notepad_open", "desktop", False),
        ("office_save_as_pdf", "desktop", False),
        ("create_text_file", "filesystem", False),
        ("screen_read_text", "desktop", False),
    ],
)
def test_reviewed_cross_domain_contracts(registry, name, resource, parallel):
    policy = policy_for(name, registry[name])
    assert policy.ordered
    assert not policy.barrier_after
    assert policy.parallel is parallel
    assert policy.resource == resource
    assert policy.reason


@pytest.mark.parametrize(
    "name, impl",
    [
        ("browser_new_magic", "browser"),
        ("computer_magic", "computer"),
        ("new_adapter_op", "adapter"),
        ("new_document_writer", "document"),
        ("web_delete", "web"),
        ("browser_interact", "mcp"),
        ("run_command", "shell"),
        ("run_skill_script", "skill_scripts"),
        ("mcp_filesystem_write_file", "mcp"),
        ("unreviewed_script", None),
    ],
)
def test_names_prefixes_and_implementation_families_do_not_grant_trust(name, impl):
    policy = policy_for(name, tool(name, impl), {"parallel": True, "selector": "#x"})
    assert not policy.ordered
    assert not policy.parallel
    assert policy.barrier_after


def test_reviewed_name_cannot_shadow_learned_or_wrong_record(registry):
    assert not policy_for(
        "web_fetch", tool("web_fetch", "web", is_learned=True)
    ).ordered
    assert not policy_for("web_fetch", registry["web_search"]).ordered
    scripted = tool("web_fetch", "web")
    scripted.script = "opaque code"
    assert not policy_for("web_fetch", scripted).ordered


@pytest.mark.parametrize("record", [None, object(), SimpleNamespace(impl="browser")])
def test_missing_metadata_defaults_to_singleton(record):
    policy = policy_for("browser_interact", record, {"selector": "#x"})
    assert not policy.ordered and not policy.parallel and policy.barrier_after


@pytest.mark.parametrize(
    "name, args",
    [
        ("browser_navigate", {"url": "https://example.com"}),
        ("browser_upload_file", {"file_path": "C:/report.pdf"}),
        ("browser_interact", {"instruction": "click the best result"}),
        ("browser_interact", {"selector": "  "}),
        ("computer_click", {"x": 100, "y": 200}),
        ("vscode_run_command", {"command_id": "some.command"}),
    ],
)
def test_state_changing_barriers_remain_ordered(registry, name, args):
    policy = policy_for(name, registry[name], args)
    assert policy.ordered and not policy.parallel and policy.barrier_after


def test_selector_interactions_use_runtime_guard_contract(registry):
    policy = policy_for(
        "browser_interact",
        registry["browser_interact"],
        {"selector": "#email", "value": "a@b.test"},
    )
    assert policy.ordered and not policy.parallel and not policy.barrier_after
    assert "revalidate" in policy.reason


@pytest.mark.parametrize(
    "combo",
    [
        "Enter",
        "return",
        "ctrl+enter",
        "ctrl+s",
        "alt+f4",
        "win+r",
        "esc",
        "unknown",
        "",
    ],
)
def test_enter_and_uncertain_hotkeys_are_barriers(registry, combo):
    policy = policy_for("computer_key", registry["computer_key"], {"combo": combo})
    assert policy.ordered and not policy.parallel and policy.barrier_after


@pytest.mark.parametrize("argument", ["combo", "key", "keys", "hotkey"])
def test_keyboard_chord_aliases_in_policy(registry, argument):
    assert not policy_for(
        "computer_key", registry["computer_key"], {argument: "Shift + Tab"}
    ).barrier_after
    assert policy_for(
        "computer_key", registry["computer_key"], {argument: "Ctrl + Enter"}
    ).barrier_after


@pytest.mark.parametrize("alias", ["key", "keys", "hotkey"])
def test_legacy_keyboard_aliases_satisfy_required_combo(registry, alias):
    result = validate_steps(
        {"step": step("computer_key", **{alias: "ctrl+enter"})}, registry, 1
    )
    assert result[0]["args"]["combo"] == "ctrl+enter"
    assert result[0]["args"][alias] == "ctrl+enter"


def test_heterogeneous_ordered_read_write_and_desktop_dependencies(registry):
    request = plan(
        step("create_text_file", filename="report.txt", content="known content"),
        step("read_document", path="C:/Users/test/Desktop/report.txt"),
        step("focus_window", title="Notepad"),
        step("computer_type", text="known text"),
        step("screen_read_text", region="active_window"),
    )
    validated = validate_steps(request, registry, remaining=8)
    assert [item["skill"] for item in validated] == [
        item["skill"] for item in request["steps"]
    ]
    assert validated[1]["args"]["path"] == "C:/Users/test/Desktop/report.txt"
    assert validated[1]["args"]["max_chars"] == "60000"


def test_document_conversion_and_web_reads_can_mix(registry):
    request = plan(
        step("office_save_as_pdf", path="C:/report.docx", out_path="C:/report.pdf"),
        step("read_document", path="C:/report.pdf"),
        step("web_fetch", url="https://example.com/known-source"),
    )
    assert len(validate_steps(request, registry, 3)) == 3


def test_observed_form_inputs_and_verification(registry):
    request = plan(
        step(
            "browser_interact",
            instruction="fill email",
            selector="#email",
            value="a@b.test",
        ),
        step(
            "browser_interact", instruction="fill name", selector="#name", value="Ada"
        ),
        step("browser_read_full"),
    )
    assert len(validate_steps(request, registry, 3)) == 3


def test_barriers_are_not_silently_removed_or_truncated(registry):
    request = plan(
        step("web_fetch", url="https://example.com/source"),
        step("browser_navigate", url="https://example.com/form"),
        step("browser_read_full"),
    )
    result = validate_steps(request, registry, 3)
    assert len(result) == 3
    assert policy_for(
        result[1]["skill"], registry[result[1]["skill"]], result[1]["args"]
    ).barrier_after


@pytest.mark.parametrize(
    "case",
    [
        {"step": {"skill": "current_time"}},
        {"kind": "action", "step": {"skill": "current_time", "args": {}}},
        {"kind": "action", "steps": [{"skill": "current_time", "args": {}}]},
        {"action": "current_time"},
        {"kind": "action", "action": "current_time", "args": {}},
        {
            "kind": "action",
            "action": "current_time",
            "args": {},
            "step": {"skill": "current_time", "args": {}},
        },
        {"step": {}, "steps": [{"skill": "current_time"}]},
        {"step": {"skill": "current_time"}, "steps": []},
    ],
)
def test_single_action_compatibility(registry, case):
    assert validate_steps(case, registry, 1) == [step("current_time")]


@pytest.mark.parametrize(
    "case",
    [
        None,
        [],
        "action",
        {},
        {"kind": "done"},
        {"steps": []},
        {"step": {}},
        {"step": []},
        {"steps": {}},
        {"steps": "not an array"},
        {"steps": [None]},
        {"steps": [False]},
        {"steps": ["current_time"]},
        {"steps": [{}]},
        {"steps": [{"skill": 1}]},
        {"steps": [{"skill": "  "}]},
        {"steps": [{"skill": "current_time", "args": []}]},
        {"steps": [{"skill": "current_time", "args": None}]},
        {"steps": [{"skill": "current_time", "why": 7}]},
        {"step": {"skill": "current_time"}, "steps": [{"skill": "current_time"}]},
        {"action": "wrong_tool", "step": {"skill": "current_time"}},
    ],
)
def test_malformed_plans_reject_whole_response(registry, case):
    with pytest.raises(ValueError):
        validate_steps(case, registry, 10)


@pytest.mark.parametrize(
    "bad", [None, {"skill": "made_up"}, {"skill": "web_fetch", "args": []}]
)
def test_invalid_later_member_does_not_return_valid_prefix(registry, bad):
    request = plan(step("current_time"), bad)
    snapshot = copy.deepcopy(request)
    with pytest.raises(ValueError):
        validate_steps(request, registry, 2)
    assert request == snapshot


def test_unknown_later_member_preflight_precedes_singleton_eligibility(registry):
    with pytest.raises(ValueError, match="Unknown tool 'made_up'"):
        validate_steps(
            plan(step("run_command", command="echo hello"), step("made_up")),
            registry,
            2,
        )


@pytest.mark.parametrize(
    "name", ["remember_fact", "recall_memory", "build_tool", "repair_tool"]
)
def test_existing_brain_builtins_are_singletons(registry, name):
    assert validate_steps({"step": step(name)}, registry, 1) == [step(name)]
    with pytest.raises(ValueError, match="singleton"):
        validate_steps(plan(step(name), step("current_time")), registry, 2)


def test_only_existing_playbook_meta_is_allowed(tmp_path, monkeypatch, registry):
    monkeypatch.setenv("WINBROW_SKILLS_DIR", str(tmp_path))
    import winbrow.brain.skill_registry as skills

    calls = []

    def load(path, **kwargs):
        calls.append((path, kwargs))
        return {"playbook_reviewed": SimpleNamespace(kind="playbook")}

    monkeypatch.setattr(skills, "load_skill_registry", load)
    assert validate_steps({"step": step("playbook_reviewed")}, registry, 1)
    with pytest.raises(ValueError, match="Unknown tool"):
        validate_steps({"step": step("playbook_invented")}, registry, 1)
    with pytest.raises(ValueError, match="singleton"):
        validate_steps(
            plan(step("playbook_reviewed"), step("current_time")), registry, 2
        )
    assert all(kwargs == {"sync_learned": False} for _, kwargs in calls)


def test_playbook_batch_rejection_explains_how_to_load_it(
    tmp_path, monkeypatch, registry
):
    monkeypatch.setenv("WINBROW_SKILLS_DIR", str(tmp_path))
    import winbrow.brain.skill_registry as skills

    monkeypatch.setattr(
        skills,
        "load_skill_registry",
        lambda path, **kwargs: {"playbook_reviewed": SimpleNamespace(kind="playbook")},
    )
    with pytest.raises(ValueError, match="load it alone"):
        validate_steps(
            plan(step("playbook_reviewed"), step("current_time")), registry, 2
        )


def test_meta_preflight_does_not_create_missing_skill_directory(
    tmp_path, monkeypatch, registry
):
    root = tmp_path / "not-created"
    monkeypatch.setenv("WINBROW_SKILLS_DIR", str(root))
    with pytest.raises(ValueError, match="Unknown tool"):
        validate_steps({"step": step("playbook_unknown")}, registry, 1)
    assert not root.exists()


def test_legacy_registry_objects_are_valid_singletons():
    registry = {"legacy_action": object()}
    assert validate_steps(
        {"action": "legacy_action", "args": {"optional": 1}}, registry, 1
    )
    with pytest.raises(ValueError, match="singleton"):
        validate_steps(
            plan(step("legacy_action", x=1), step("legacy_action", x=2)), registry, 2
        )


@pytest.mark.parametrize(
    "name",
    ["run_command", "run_skill_script", "mcp_filesystem_write_file", "learned_action"],
)
def test_opaque_tools_are_singletons_not_permanently_banned(registry, name):
    assert validate_steps({"step": step(name)}, registry, 1)
    with pytest.raises(ValueError, match="singleton"):
        validate_steps(plan(step(name), step("current_time")), registry, 2)


@pytest.mark.parametrize(
    "name", ["mcp_filesystem_write_file", "run_skill_script", "learned_action"]
)
def test_opaque_contract_can_be_reviewed_without_a_category_ban(
    monkeypatch, registry, name
):
    from winbrow.brain import batching

    reviewed = BatchPolicy(
        True, False, False, "filesystem", "Reviewed exact operation."
    )
    record = registry[name]
    table = batching._REVIEWED_LEARNED if record.is_learned else batching._REVIEWED
    monkeypatch.setitem(table, (name, record.impl), reviewed)
    request = plan(
        step(name, path="C:/known.txt", content="known"),
        step("read_document", path="C:/known.txt"),
    )
    assert len(validate_steps(request, registry, 2)) == 2


def test_cap_and_budget_reject_instead_of_clipping(monkeypatch, registry):
    request = plan(*(step("current_time") for _ in range(6)))
    with pytest.raises(ValueError, match="cap 5"):
        validate_steps(request, registry, 20)
    monkeypatch.setenv("WINBROW_MAX_ACTIONS_PER_TURN", "10")
    assert len(validate_steps(request, registry, 6)) == 6
    with pytest.raises(ValueError, match="remaining budget 5"):
        validate_steps(request, registry, 5)
    with pytest.raises(ValueError, match="cap 3"):
        validate_steps(request, registry, 20, limit=3)
    monkeypatch.setenv("WINBROW_MAX_ACTIONS_PER_TURN", "2")
    with pytest.raises(ValueError, match="cap 2"):
        validate_steps(request, registry, 20, limit=10)
    with pytest.raises(ValueError, match="remaining budget 0"):
        validate_steps({"step": step("current_time")}, registry, 0)


def test_hard_ceiling_cannot_be_overridden(monkeypatch, registry):
    monkeypatch.setenv("WINBROW_MAX_ACTIONS_PER_TURN", "1000")
    with pytest.raises(ValueError, match="cap 10"):
        validate_steps(
            plan(*(step("current_time") for _ in range(11))), registry, 1000, limit=1000
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"remaining": -1},
        {"remaining": True},
        {"remaining": "5"},
        {"remaining": 5, "limit": 0},
        {"remaining": 5, "limit": "5"},
        {"remaining": 5, "limit": True},
    ],
)
def test_malformed_limits(registry, kwargs):
    with pytest.raises(ValueError):
        validate_steps({"step": step("current_time")}, registry, **kwargs)


def test_required_defaults_enum_and_optional_legacy_args(registry):
    registry["enum_test"] = tool(
        "enum_test",
        args=[
            ArgSpec("required_text", "text", ""),
            ArgSpec(
                "mode",
                "enum",
                "",
                criteria={"up": "ascending", "down": "descending"},
                default="up",
            ),
        ],
    )
    request = {
        "step": step("enum_test", required_text="", optional={"items": [1, True, None]})
    }
    snapshot = copy.deepcopy(request)
    result = validate_steps(request, registry, 1)
    assert result[0]["args"] == {
        "required_text": "",
        "mode": "up",
        "optional": {"items": [1, True, None]},
    }
    assert request == snapshot
    for args in (
        {},
        {"required_text": "x", "mode": "ascending"},
        {"required_text": []},
        {"required_text": None},
    ):
        with pytest.raises(ValueError):
            validate_steps({"step": {"skill": "enum_test", "args": args}}, registry, 1)


def test_optional_null_text_and_single_item_array_are_normalized(registry):
    registry["path_like"] = tool(
        "path_like",
        args=[
            ArgSpec("cwd", "text", "", default=""),
            ArgSpec("path", "text", "", required=False),
            ArgSpec("wrapped", "text", "", required=False),
        ],
    )
    result = validate_steps(
        {
            "step": step(
                "path_like",
                cwd=None,
                path=["C:\\work"],
                wrapped={"path": "C:\\wrapped"},
            )
        },
        registry,
        1,
    )
    assert result[0]["args"] == {
        "cwd": "",
        "path": "C:\\work",
        "wrapped": "C:\\wrapped",
    }


def test_required_text_single_item_array_is_unwrapped(registry):
    registry["required_like"] = tool(
        "required_like", args=[ArgSpec("value", "text", "", required=True)]
    )
    result = validate_steps(
        {"step": step("required_like", value=["only"])}, registry, 1
    )
    assert result[0]["args"] == {"value": "only"}


def test_non_scalar_text_argument_reports_skill_and_value(registry):
    registry["cwd_like"] = tool(
        "cwd_like", args=[ArgSpec("cwd", "text", "", default="")]
    )
    with pytest.raises(
        ValueError, match=r"Step 1 \('cwd_like'\).*Argument 'cwd'.*list.*two"
    ):
        validate_steps(
            {"step": step("cwd_like", cwd=["one", "two"])}, registry, 1
        )


@pytest.mark.parametrize(
    "value, expected",
    [
        ("deskTOP", "Desktop"),
        ('"Downloads"', "Downloads"),
        ("the Documents folder", "Documents"),
        ("C:\\Users\\me\\Desktop", "Desktop"),
        ("C:\\Users\\me\\Desktop\\", "Desktop"),
        ("~/Pictures", "Pictures"),
        (["Desktop"], "Desktop"),
    ],
)
def test_enum_accepts_safe_spelling_variants(registry, value, expected):
    registry["folder_enum"] = tool(
        "folder_enum",
        args=[
            ArgSpec(
                "folder",
                "enum",
                "",
                criteria={
                    "Pictures": "pictures",
                    "Downloads": "downloads",
                    "Desktop": "desktop",
                    "Documents": "documents",
                },
                default="Pictures",
            )
        ],
    )
    result = validate_steps(
        {"step": step("folder_enum", folder=value)}, registry, 1
    )
    assert result[0]["args"]["folder"] == expected


def test_enum_absolute_subfolder_still_rejects_with_the_value(registry):
    registry["folder_enum"] = tool(
        "folder_enum",
        args=[
            ArgSpec(
                "folder",
                "enum",
                "",
                criteria={"Desktop": "desktop", "Downloads": "downloads"},
                default="Desktop",
            )
        ],
    )
    with pytest.raises(ValueError, match="allowed enum value") as info:
        validate_steps(
            {
                "step": step(
                    "folder_enum", folder="C:\\Users\\me\\Desktop\\deck"
                )
            },
            registry,
            1,
        )
    assert "Desktop" in str(info.value) and "deck" in str(info.value)


def test_explicit_optional_arg_may_be_omitted(registry):
    registry["mcp_like"] = tool(
        "mcp_like",
        args=[
            ArgSpec("query", "text", ""),
            ArgSpec("max_results", "text", "", required=False),
        ],
    )
    result = validate_steps(
        {"step": step("mcp_like", query="diffusion")}, registry, 1
    )
    assert result[0]["args"] == {"query": "diffusion"}


def test_explicit_required_arg_is_enforced_without_a_default(registry):
    registry["mcp_required"] = tool(
        "mcp_required",
        args=[ArgSpec("paper_id", "text", "", required=True)],
    )
    with pytest.raises(ValueError, match="Missing required argument 'paper_id'"):
        validate_steps({"step": step("mcp_required")}, registry, 1)


def test_explicit_required_arg_wins_over_a_default(registry):
    registry["seed_like"] = tool(
        "seed_like",
        args=[ArgSpec("target", "text", "", default="note.txt", required=True)],
    )
    with pytest.raises(ValueError, match="Missing required argument 'target'"):
        validate_steps({"step": step("seed_like")}, registry, 1)
    result = validate_steps({"step": step("seed_like", target="a.txt")}, registry, 1)
    assert result[0]["args"]["target"] == "a.txt"


def test_browser_interact_accepts_a_selector_without_an_instruction(registry):
    result = validate_steps(
        {"step": step("browser_interact", selector="#submit")}, registry, 1
    )
    assert result[0]["args"]["selector"] == "#submit"
    assert result[0]["args"]["instruction"] == ""


def test_json_array_argument_is_accepted(registry):
    registry["mcp_json_like"] = tool(
        "mcp_json_like",
        args=[
            ArgSpec("path", "text", ""),
            ArgSpec("excludePatterns", "json", "", required=False),
        ],
    )
    result = validate_steps(
        {
            "step": step(
                "mcp_json_like",
                path="C:\\work",
                excludePatterns=["node_modules", ".git"],
            )
        },
        registry,
        1,
    )
    assert result[0]["args"]["excludePatterns"] == ["node_modules", ".git"]


def test_json_one_item_array_stays_an_array(registry):
    registry["mcp_json_like"] = tool(
        "mcp_json_like",
        args=[
            ArgSpec("path", "text", ""),
            ArgSpec("excludePatterns", "json", "", required=False),
        ],
    )
    result = validate_steps(
        {
            "step": step(
                "mcp_json_like",
                path="C:\\work",
                excludePatterns=["node_modules"],
            )
        },
        registry,
        1,
    )
    assert result[0]["args"]["excludePatterns"] == ["node_modules"]


def test_run_command_accepts_null_or_one_item_cwd(registry):
    from winbrow.shell import get_shell_tools

    for record in get_shell_tools():
        registry[record.name] = record
    result = validate_steps(
        {
            "step": {
                "skill": "run_command",
                "args": {"command": "dir", "cwd": ["C:\\work"]},
            }
        },
        registry,
        1,
    )
    assert result[0]["args"]["cwd"] == "C:\\work"
    result = validate_steps(
        {
            "step": {
                "skill": "run_command",
                "args": {"command": "dir", "cwd": None},
            }
        },
        registry,
        1,
    )
    assert result[0]["args"]["cwd"] == ""


def test_download_images_accepts_an_absolute_folder(registry):
    from winbrow.image_tools import get_image_tools

    for record in get_image_tools():
        registry[record.name] = record
    result = validate_steps(
        {
            "step": {
                "skill": "download_images",
                "args": {
                    "query": "eiffel tower",
                    "folder": "D:\\projects\\deck\\assets",
                },
            }
        },
        registry,
        1,
    )
    assert result[0]["args"]["folder"] == "D:\\projects\\deck\\assets"


def test_run_skill_script_accepts_an_object_spec(registry):
    from winbrow.skill_scripts import get_skill_script_tools

    for record in get_skill_script_tools():
        registry[record.name] = record
    spec = {"operation": "merge", "inputs": ["a.pdf", "b.pdf"]}
    result = validate_steps(
        {
            "step": {
                "skill": "run_skill_script",
                "args": {
                    "skill": "pdf",
                    "script": "pdf_tool.py",
                    "spec": spec,
                },
            }
        },
        registry,
        1,
    )
    assert result[0]["args"]["spec"] == spec


@pytest.mark.parametrize(
    "freshness, expected",
    [
        ("", ""),
        ("Day", "day"),
        ("today", "day"),
        ("recent", "week"),
        ("this week", "week"),
        ("past month", "month"),
        ("any", ""),
    ],
)
def test_optional_empty_enum_default_and_recency_aliases(
    registry, freshness, expected
):
    result = validate_steps(
        {"step": step("web_search", query="x", freshness=freshness)}, registry, 1
    )
    assert result[0]["args"]["freshness"] == expected


def test_omitted_optional_enum_defaults_without_rejection(registry):
    result = validate_steps({"step": step("web_search", query="x")}, registry, 1)
    assert result[0]["args"]["freshness"] == ""


def test_unknown_enum_value_still_rejects(registry):
    with pytest.raises(ValueError, match="allowed enum value"):
        validate_steps(
            {"step": step("web_search", query="x", freshness="someday")},
            registry,
            1,
        )


def test_installer_package_helper_accepts_aliases():
    from winbrow.installer import package_from_args

    assert package_from_args({"package": "7zip.7zip"}) == "7zip.7zip"
    assert package_from_args({"app": "7zip"}) == "7zip"
    assert package_from_args({"app_name": "  spotify  "}) == "spotify"
    assert package_from_args({"name": "vlc"}) == "vlc"
    assert package_from_args({}) == ""


def test_installer_package_aliases_are_normalized(registry):
    for alias in (
        "app",
        "app_name",
        "app_id",
        "application",
        "name",
        "package_name",
        "package_id",
        "winget_id",
        "query",
        "software",
        "program",
    ):
        result = validate_steps(
            {"step": {"skill": "app_install", "args": {alias: "7zip"}}},
            registry,
            1,
        )
        assert result[0]["args"]["package"] == "7zip"
    with pytest.raises(ValueError, match="Missing required argument 'package'"):
        validate_steps({"step": step("app_install")}, registry, 1)


def test_installer_package_accepts_a_one_item_array(registry):
    result = validate_steps(
        {"step": step("app_install", app_name=["7zip"])}, registry, 1
    )
    assert result[0]["args"]["package"] == "7zip"


def test_numeric_json_scalars_work_for_legacy_text_args(registry):
    result = validate_steps(
        {"step": step("computer_click", x=100, y=200, double=False)}, registry, 1
    )
    assert result[0]["args"]["x"] == 100
    assert result[0]["args"]["double"] is False


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        object(),
        {1: "bad key"},
        {"nested": [{"$ref": "steps[0].output"}]},
        "${steps[0].output}",
        "{{steps.0.url}}",
        "$results[0].path",
        "${output}",
    ],
)
def test_malformed_json_or_unresolved_references(registry, value):
    with pytest.raises(ValueError):
        validate_steps({"step": step("current_time", optional=value)}, registry, 1)


def test_literal_templates_and_known_values_are_not_interpreted(registry):
    value = "Literal {{title}}, $HOME and C:/known/file.txt"
    result = validate_steps({"step": step("computer_type", text=value)}, registry, 1)
    assert result[0]["args"]["text"] == value


def test_exact_repeated_mutation_is_conflicting_even_with_different_why(registry):
    first = step("browser_interact", instruction="toggle option", selector="#option")
    second = dict(first, why="repeat it", parallel=True)
    with pytest.raises(ValueError, match="Conflicting repeated mutation"):
        validate_steps(plan(first, step("browser_read_full"), second), registry, 3)
    with pytest.raises(ValueError, match="Conflicting repeated mutation"):
        validate_steps(
            plan(step("paint_invert_colors"), step("paint_invert_colors")), registry, 2
        )


def test_repeated_reads_and_distinct_mutations_are_valid(registry):
    request = plan(
        step("browser_read_full"),
        step("browser_interact", instruction="fill x", selector="#x", value="x"),
        step("browser_interact", instruction="fill y", selector="#y", value="y"),
        step("browser_read_full"),
    )
    assert len(validate_steps(request, registry, 4)) == 4


@pytest.mark.parametrize(
    "allowed", [lambda name: name == "current_time", {"current_time"}]
)
def test_subagent_scope_covers_every_member(registry, allowed):
    assert validate_steps(
        {"step": step("current_time")}, registry, 1, allowed_skills=allowed
    )
    with pytest.raises(ValueError, match="not available to this subagent"):
        validate_steps(
            plan(step("current_time"), step("read_document", path="C:/secret.txt")),
            registry,
            2,
            allowed_skills=allowed,
        )
    with pytest.raises(ValueError, match="not available to this subagent"):
        validate_steps(
            {"step": step("remember_fact", fact="secret")},
            registry,
            1,
            allowed_skills=allowed,
        )


def test_schema_keeps_single_step_and_bounds_array():
    properties = PLANNER_JSON_SCHEMA["properties"]
    assert properties["step"]["required"] == ["skill", "args"]
    assert properties["steps"]["minItems"] == 1
    assert properties["steps"]["maxItems"] == 10
    assert properties["steps"]["items"]["required"] == ["skill", "args"]


def test_prompt_promotes_general_known_input_batches_without_old_contradictions():
    prompt = SYSTEM_PROMPT_STATIC
    for phrase in [
        "mixed tools and mixed reads/writes are allowed",
        "Ordered dependencies",
        "read-after-write",
        "remaining action budget",
        "run_skill()",
        "permission gate",
        "future-output placeholders",
        "reviewed reads",
        "runtime page/target state",
        "WINBROW_MAX_ACTIONS_PER_TURN",
        "clamps to 1..10",
        "invalid\n     values fall back to 5",
    ]:
        assert phrase in prompt
    for phrase in [
        "Emit ONE",
        "2-3 call read-only batch",
        "Never mix a read with a write",
        "your next step must observe",
        "Emit the next single action",
        "single best next action",
    ]:
        assert phrase not in prompt + BROWSER_BREVITY
    for preserved in [
        "WEB ACCESS HIERARCHY",
        "delegate_task",
        "FOLLOW-UP ARTIFACTS",
        "PLAYBOOK SKILLS",
        "PRESENTATIONS vs PAPER DOCUMENTS",
        "ANSWER QUALITY",
        "DONE IS A STATE",
    ]:
        assert preserved in prompt


def test_both_prompt_builders_use_live_cap_and_bounded_browser_batch(monkeypatch):
    monkeypatch.setenv("WINBROW_MAX_ACTIONS_PER_TURN", "3")
    messages = build_loop_messages(
        "goal", "history", "ctx", "memory", "", steps_remaining=2, browser_turn=True
    )
    content = messages[1]["content"]
    assert "MAX ACTIONS THIS TURN: 2" in content
    assert BROWSER_BREVITY in content
    assert "best next action or bounded known-input batch" in content
    assert content.index("HISTORY:") < content.index("MAX ACTIONS THIS TURN:")
    direct = build_planner_message(
        "goal", [{"skill": "browser_read_full"}], steps_remaining=7
    )
    assert "MAX ACTIONS THIS TURN: 3" in direct
    assert BROWSER_BREVITY in direct
    assert "single best next action" not in content + direct
    monkeypatch.setenv("WINBROW_MAX_ACTIONS_PER_TURN", "1")
    assert "MAX ACTIONS THIS TURN: 1" in build_planner_message("goal", [])
    assert "MAX ACTIONS THIS TURN: 0" in build_planner_message(
        "goal", [], steps_remaining=0
    )
