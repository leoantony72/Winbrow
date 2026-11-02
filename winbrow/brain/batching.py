"""Backend-owned batch contracts and all-or-nothing planner preflight.

Eligibility is not permission or proof of success. The executor must still gate
each member through run_skill(), verify resource state, and stop at barriers.
Add reviewed (name, impl) records here, never trust planner/MCP-supplied flags.
"""

from __future__ import annotations

import json
import math
import ntpath
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

HARD_MAX_ACTIONS_PER_TURN = 10
_DEFAULT_MAX_ACTIONS = 5


def max_actions_per_turn() -> int:
    """Read WINBROW_MAX_ACTIONS_PER_TURN at call time; default 5, clamp 1..10."""
    try:
        value = int(os.environ.get("WINBROW_MAX_ACTIONS_PER_TURN", "5"))
    except (TypeError, ValueError):
        value = _DEFAULT_MAX_ACTIONS
    return max(1, min(HARD_MAX_ACTIONS_PER_TURN, value))


@dataclass(frozen=True)
class BatchPolicy:
    ordered: bool
    parallel: bool
    barrier_after: bool
    resource: str
    reason: str


_UNKNOWN = BatchPolicy(
    False, False, True, "unknown", "No reviewed execution contract; use a singleton."
)
_BROWSER_READ = BatchPolicy(
    True, False, False, "browser", "Read shared agent-tab state in order."
)
_BROWSER_WRITE = BatchPolicy(
    True,
    False,
    False,
    "browser",
    "Known selector; runtime must revalidate page and target state.",
)
_BROWSER_BARRIER = BatchPolicy(
    True,
    False,
    True,
    "browser",
    "Navigation, upload or unresolved interaction requires fresh observation.",
)
_DESKTOP = BatchPolicy(
    True,
    False,
    False,
    "desktop",
    "Ordered desktop operation; verify window, focus and effect before continuing.",
)
_DESKTOP_BARRIER = BatchPolicy(
    True,
    False,
    True,
    "desktop",
    "May submit, change focus or open a dialog; observe before continuing.",
)
_FILE_WRITE = BatchPolicy(
    True,
    False,
    False,
    "filesystem",
    "Known destination and content; verify the resulting file.",
)
_FILE_READ = BatchPolicy(
    True,
    True,
    False,
    "filesystem",
    "Reviewed read; parallel only with independent inputs and no conflicting writes.",
)
_WEB_READ = BatchPolicy(
    True,
    True,
    False,
    "web",
    "Reviewed HTTP read; parallel only when inputs are independent.",
)
_SYSTEM = BatchPolicy(
    True,
    False,
    False,
    "system",
    "Reviewed system setting; verify the reported result before continuing.",
)

# Exact names AND dispatcher implementations: an unfamiliar operation in a known
# implementation is not automatically safe. None entries are reviewed legacy
# seed reads or name-specific native dispatch branches in WinBrowAgent.run_skill.
_REVIEWED = {
    ("web_search", "web"): _WEB_READ,
    ("web_fetch", "web"): _WEB_READ,
    ("read_document", "document"): _FILE_READ,
    ("find_files", None): _FILE_READ,
    ("current_time", None): BatchPolicy(
        True, True, False, "clock", "Reviewed clock read."
    ),
    ("create_text_file", None): _FILE_WRITE,
    ("volume_set_level", None): _SYSTEM,
    ("app_focus_or_launch", None): _DESKTOP,
    ("type_text", None): _DESKTOP,
    ("browser_navigate", "browser"): _BROWSER_BARRIER,
    ("browser_upload_file", "browser"): _BROWSER_BARRIER,
    ("browser_interact", "browser"): _BROWSER_WRITE,
    ("browser_read_page", "browser"): _BROWSER_READ,
    ("browser_read_full", "browser"): _BROWSER_READ,
    ("browser_get_accessibility_tree", "browser"): _BROWSER_READ,
    ("browser_wait", "browser"): _BROWSER_READ,
    ("focus_window", "computer"): _DESKTOP,
    ("wait_for_window", "computer"): _DESKTOP,
    ("computer_type", "computer"): _DESKTOP,
    ("computer_scroll", "computer"): _DESKTOP,
    ("computer_key", "computer"): _DESKTOP_BARRIER,
    ("computer_click", "computer"): _DESKTOP_BARRIER,
    ("computer_click_text", "computer"): _DESKTOP_BARRIER,
    ("minimize_all_except", "computer"): _DESKTOP_BARRIER,
    ("file_dialog_save", "computer"): _DESKTOP_BARRIER,
    ("screen_read_text", "computer"): BatchPolicy(
        True, False, False, "desktop", "Read the shared foreground desktop in order."
    ),
    ("notepad_open", "adapter"): _DESKTOP,
    ("notepad_save_as", "adapter"): _DESKTOP_BARRIER,
    ("paint_open_image", "adapter"): _DESKTOP,
    ("paint_invert_colors", "adapter"): _DESKTOP,
    ("paint_save_copy", "adapter"): _DESKTOP_BARRIER,
    ("office_open_doc", "adapter"): _DESKTOP_BARRIER,
    ("office_save_as_pdf", "adapter"): _DESKTOP,
    ("photoshop_open_image", "adapter"): _DESKTOP_BARRIER,
    ("photoshop_desaturate", "adapter"): _DESKTOP,
    ("photoshop_save_as", "adapter"): _DESKTOP,
    ("vscode_open", "adapter"): _DESKTOP_BARRIER,
    ("vscode_install_extension", "adapter"): _DESKTOP_BARRIER,
    ("vscode_run_command", "adapter"): _DESKTOP_BARRIER,
    ("vscode_list_extensions", "adapter"): BatchPolicy(
        True, True, False, "vscode", "Reviewed installed-extension read."
    ),
    ("aftereffects_detect", "adapter"): BatchPolicy(
        True, True, False, "filesystem", "Reviewed renderer-presence read."
    ),
    ("aftereffects_render_comp", "adapter"): BatchPolicy(
        True,
        False,
        True,
        "filesystem",
        "Long-running render; verify the artifact before continuing.",
    ),
}
# Reviewing a learned definition must be explicit; a learned tool cannot inherit
# the contract of a native tool it happens to share a name with.
_REVIEWED_LEARNED: dict[tuple[str, str | None], BatchPolicy] = {}
_READ_KEYS = frozenset(
    {
        ("web_search", "web"),
        ("web_fetch", "web"),
        ("read_document", "document"),
        ("find_files", None),
        ("current_time", None),
        ("browser_read_page", "browser"),
        ("browser_read_full", "browser"),
        ("browser_get_accessibility_tree", "browser"),
        ("browser_wait", "browser"),
        ("screen_read_text", "computer"),
        ("vscode_list_extensions", "adapter"),
        ("aftereffects_detect", "adapter"),
    }
)
_BRAIN_BUILTINS = frozenset(
    {"remember_fact", "recall_memory", "build_tool", "repair_tool"}
)
_SAFE_KEYS = frozenset(
    {"tab", "shift+tab", "left", "right", "up", "down", "home", "end"}
)


def policy_for(tool_name: str, tool=None, args=None) -> BatchPolicy:
    """Return a trusted contract, or a singleton barrier for opaque tools.

    A real registry record is required for reviewed tools. Legacy registry stubs
    (object()) remain executable as singletons but cannot grant batch eligibility.
    Opaque script/learned/MCP tools can gain eligibility by adding reviewed records;
    their category, permission tier and external descriptions grant none by default.
    """
    if tool is None or getattr(tool, "name", None) != tool_name:
        return _UNKNOWN
    impl = getattr(tool, "impl", None)
    if not isinstance(impl, (str, type(None))):
        return _UNKNOWN
    reviewed = _REVIEWED_LEARNED if getattr(tool, "is_learned", False) else _REVIEWED
    policy = reviewed.get((tool_name, impl), _UNKNOWN)
    if policy is _UNKNOWN:
        return policy
    # Python-backed records should not carry a second, opaque script contract.
    if impl is not None and getattr(tool, "script", ""):
        return _UNKNOWN
    args = args if isinstance(args, dict) else {}
    if tool_name == "browser_interact":
        selector = args.get("selector")
        if not isinstance(selector, str) or not selector.strip():
            return _BROWSER_BARRIER
    if tool_name == "computer_key":
        combo = (
            args.get("combo")
            or args.get("key")
            or args.get("keys")
            or args.get("hotkey")
        )
        if isinstance(combo, str) and combo.lower().replace(" ", "") in _SAFE_KEYS:
            return _DESKTOP
    return policy


# Result bindings are intentionally not a feature of this first-release format.
# Restrict the pattern to explicit step/result placeholders, not ordinary prose,
# URLs, PowerShell variables, or literal template content such as {{title}}.
_RESULT_REF = re.compile(
    r"(?:\$\{\s*|\{\{\s*|\$)(?:steps?|actions?|results?|outputs?)\d*(?:[.\[]|\s*[}\]])",
    re.IGNORECASE,
)


def _validate_json(value) -> None:
    if isinstance(value, str):
        if _RESULT_REF.search(value):
            raise ValueError(
                "Unresolved result reference: all action inputs must already be known."
            )
    elif isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("Argument object keys must be strings.")
            if key == "$ref":
                raise ValueError(
                    "Unresolved result reference: $ref bindings are not supported."
                )
            _validate_json(item)
    elif isinstance(value, list):
        for item in value:
            _validate_json(item)
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Arguments must contain finite JSON numbers.")
    elif value is not None and not isinstance(value, (bool, int)):
        raise ValueError("Arguments must contain only JSON values.")


_INSTALLER_PACKAGE_TOOLS = frozenset(
    {"app_search", "app_install", "app_uninstall"}
)


def _normalize_known_aliases(tool_name: str, args: dict) -> None:
    """Apply small, tool-specific aliases before generic argument validation."""
    if tool_name == "computer_key" and not args.get("combo"):
        for alias in ("key", "keys", "hotkey"):
            if args.get(alias):
                args["combo"] = args[alias]
                break
    if tool_name in _INSTALLER_PACKAGE_TOOLS:
        from ..installer import package_from_args

        package = package_from_args(args)
        if package:
            args["package"] = package


class StepArgumentError(ValueError):
    """Planner argument mismatch tied to the step that needs correction."""

    def __init__(self, message: str, skill: str = "", index: int = 0):
        super().__init__(message)
        self.skill = skill
        self.index = index


def _preview(value, limit: int = 120) -> str:
    """Single-line, bounded JSON preview for planner feedback and traces."""
    try:
        text = json.dumps(value, ensure_ascii=False, default=repr)
    except (TypeError, ValueError):
        text = repr(value)
    text = " ".join(str(text).split())
    if len(text) > limit:
        text = text[: limit - 3] + "..."
    return text


_SCALAR_WRAPPER_KEYS = frozenset(
    {"path", "value", "text", "cwd", "workdir", "directory", "dir", "folder"}
)


_REDACT_ARG_NAMES = frozenset(
    {
        "api_key",
        "authorization",
        "body",
        "content",
        "cookie",
        "password",
        "secret",
        "text",
        "token",
    }
)


def _arg_preview(name: str, value) -> str:
    """Shape-only feedback for user content or credentials."""
    if str(name).lower() in _REDACT_ARG_NAMES:
        return f"<{type(value).__name__}>"
    return _preview(value)


def _unwrapped_scalar(value):
    """Accept the common planner mistake of wrapping one value in an array/object."""
    if (
        isinstance(value, (list, tuple))
        and len(value) == 1
        and isinstance(value[0], (str, int, float, bool))
    ):
        return value[0]
    if isinstance(value, dict) and len(value) == 1:
        key, inner = next(iter(value.items()))
        if (
            str(key).lower() in _SCALAR_WRAPPER_KEYS
            and isinstance(inner, (str, int, float, bool))
        ):
            return inner
    return value


def _enum_match(value: str, lookup: dict[str, object]):
    """Resolve articles, a trailing 'folder' and path basenames."""
    direct = lookup.get(value.lower())
    if direct is not None:
        return direct
    cleaned = re.sub(r"^the\s+", "", value, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\s+(?:folder|directory|dir)$", "", cleaned, flags=re.IGNORECASE
    ).strip()
    direct = lookup.get(cleaned.lower())
    if direct is not None:
        return direct
    if "/" in value or "\\" in value:
        # C:\Users\me\Desktop or ~/Desktop -> the final path component.
        base = ntpath.basename(value.replace("/", "\\").rstrip("\\"))
        direct = lookup.get(base.strip().lower())
        if direct is not None:
            return direct
    return None


def _arguments(tool, supplied: dict) -> dict:
    args = dict(supplied)
    tool_name = str(getattr(tool, "name", "") or "")
    _normalize_known_aliases(tool_name, args)
    specs = getattr(tool, "args", ()) if tool is not None else ()
    # Legacy fake registry records need not implement Tool/ArgSpec.
    if not isinstance(specs, (list, tuple)):
        specs = ()
    for spec in specs:
        name = getattr(spec, "name", None)
        if not isinstance(name, str):
            continue
        default = getattr(spec, "default", None)
        explicit_required = getattr(spec, "required", None)
        required = (
            default is None if explicit_required is None
            else bool(explicit_required)
        )
        if name not in args:
            if required:
                raise ValueError(
                    f"Missing required argument '{name}' for '{tool_name}'."
                )
            if default is not None:
                args[name] = default
            else:
                continue
        value = args[name]
        if value is None:
            # Planners commonly send null for an optional unknown they do not
            # want to set. Treat it as omitted instead of failing the whole plan.
            if required:
                raise ValueError(
                    f"Missing required argument '{name}' for '{tool_name}'."
                )
            if default is not None:
                args[name] = default
            else:
                args.pop(name, None)
            continue
        kind = getattr(spec, "kind", getattr(spec, "type", "text"))
        if kind in {"text", "string", "enum"}:
            # Unwrap only scalar kinds. A one-item array is still an array for
            # a JSON-kind MCP argument such as `excludePatterns`.
            value = _unwrapped_scalar(value)
            args[name] = value
        if kind == "json":
            # Arrays/objects are validated by _validate_json below.
            pass
        elif kind in {"text", "string"} and not isinstance(
            value, (str, int, float, bool)
        ):
            raise ValueError(
                f"Argument '{name}' for '{tool_name}' must be text or a scalar "
                f"value; got {type(value).__name__} "
                f"{_arg_preview(name, value)}. "
                "Pass one string, not an array or object."
            )
        if kind == "enum":
            choices = getattr(spec, "criteria", {}) or {}
            if isinstance(value, (int, float, bool)):
                value = str(value)
            if isinstance(value, str):
                # Optional enums commonly use "" as the "no filter" default,
                # and planners may send a recency alias ("today", "recent").
                if tool_name == "web_search" and name == "freshness":
                    from ..web_tools import canonical_freshness

                    value = canonical_freshness(value)
                value = value.strip().strip('"').strip("'").strip()
                lookup = {str(choice).lower(): choice for choice in choices}
                matched = _enum_match(value, lookup)
                if matched is not None:
                    value = matched
                args[name] = value
            allowed_empty = value == "" and default == ""
            if not isinstance(value, str) or (
                choices and value not in choices and not allowed_empty
            ):
                raise ValueError(
                    f"Argument '{name}' for '{tool_name}' must be an allowed "
                    f"enum value: {list(choices)}; got "
                    f"{_arg_preview(name, args.get(name))}. "
                    "Use one exact choice."
                )
    _validate_json(args)
    return args


def _known_meta(name: str) -> bool:
    if name in _BRAIN_BUILTINS:
        return True
    if name.startswith("playbook_"):
        from .skill_registry import load_skill_registry

        root = Path(
            os.environ.get("WINBROW_SKILLS_DIR")
            or Path(__file__).resolve().parents[1] / "skills"
        )
        if not root.is_dir():
            return False
        meta = load_skill_registry(str(root), sync_learned=False).get(name)
        return meta is not None and getattr(meta, "kind", None) == "playbook"
    return False


def validate_steps(
    plan: dict,
    registry,
    remaining: int,
    limit: Optional[int] = None,
    allowed_skills=None,
) -> list[dict]:
    """Normalize/preflight an entire action response, or raise ValueError.

    Accept step, steps[], and the legacy action-name + args spelling. A supplied
    limit may lower (not increase) the configured cap. Nothing is truncated or
    dispatched. Opaque tools and brain meta/guidance calls remain valid singletons.
    Ordered heterogeneous calls and known-input dependencies are allowed; barriers
    are returned intact for the executor to split and revalidate, not ignored.
    Unknown optional arguments are preserved for legacy tool compatibility.
    """
    if not isinstance(plan, dict) or plan.get("kind", "action") != "action":
        raise ValueError("Expected an action plan object.")
    step, steps, action = plan.get("step"), plan.get("steps"), plan.get("action")
    if step is not None and not isinstance(step, dict):
        raise ValueError("step must be an object.")
    if steps is not None and not isinstance(steps, list):
        raise ValueError("steps must be an array.")
    if step and steps:
        raise ValueError("Use step or steps, not both.")
    if action and (step or steps):
        # _ask_plan may synthesize step from the legacy action spelling.
        if not (
            not steps
            and isinstance(action, str)
            and step == {"skill": action, "args": plan.get("args", {})}
        ):
            raise ValueError("Use action, step or steps, not conflicting action forms.")
    if step:
        raw = [step]
    elif steps:
        raw = steps
    elif isinstance(action, str) and action.strip():
        raw = [{"skill": action, "args": plan.get("args", {})}]
    else:
        raise ValueError("Action plan must contain at least one step.")
    cap = max_actions_per_turn()
    if limit is not None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("Action limit must be a positive integer.")
        cap = min(cap, limit)
    if len(raw) > cap:
        raise ValueError(
            f"Too many actions: {len(raw)} exceeds per-turn cap {cap}. "
            f"Return at most {cap} steps, execute that batch, then continue "
            "on the next turn."
        )
    if isinstance(remaining, bool) or not isinstance(remaining, int) or remaining < 0:
        raise ValueError("Remaining action budget must be a nonnegative integer.")
    if len(raw) > remaining:
        raise ValueError(
            f"Action count {len(raw)} exceeds remaining budget {remaining}; replan, do not truncate."
        )

    normalized, policies, identities = [], [], set()
    for index, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Step {index} must be an object.")
        name = item.get("skill")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Step {index} needs a nonempty skill name.")
        args = item.get("args", {})
        if not isinstance(args, dict):
            raise ValueError(f"Step {index} args must be an object.")
        if "why" in item and not isinstance(item["why"], str):
            raise ValueError(f"Step {index} why must be text.")
        if allowed_skills is not None:
            allowed = (
                allowed_skills(name)
                if callable(allowed_skills)
                else name in allowed_skills
            )
            if not allowed:
                raise ValueError(f"Skill '{name}' is not available to this subagent.")
        tool = registry.get(name)
        if tool is None and not _known_meta(name):
            raise ValueError(f"Unknown tool '{name}' in step {index}.")
        try:
            args = _arguments(tool, args)
        except (ValueError, TypeError) as exc:
            raise StepArgumentError(
                f"Step {index} ('{name}'): {exc}", skill=name, index=index
            ) from exc
        policy = policy_for(name, tool, args)
        record = {"skill": name, "args": args}
        if "why" in item:
            record["why"] = item["why"]
        normalized.append(record)
        policies.append(policy)
        key = (name, getattr(tool, "impl", None))
        identity = (
            name,
            json.dumps(args, sort_keys=True, ensure_ascii=False, allow_nan=False),
        )
        if key not in _READ_KEYS and identity in identities:
            raise ValueError(
                f"Conflicting repeated mutation '{name}'; do not repeat non-read actions in a batch."
            )
        identities.add(identity)

    # Check eligibility only after every member's shape/name/arguments, so an
    # opaque early member never hides a malformed or unknown later command.
    if len(normalized) > 1:
        for record, policy in zip(normalized, policies):
            if not policy.ordered:
                if str(record["skill"]).startswith("playbook_"):
                    raise ValueError(
                        f"Tool '{record['skill']}' requires a singleton: a "
                        "playbook is guidance, so load it alone and execute the "
                        "concrete tools it names on the next turn."
                    )
                raise ValueError(
                    f"Tool '{record['skill']}' requires a singleton: {policy.reason}"
                )
    return normalized
