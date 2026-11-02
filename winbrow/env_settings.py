"""App-managed environment settings stored in the project ``.env``.

The Settings tab edits the same file the server loads at startup. Writes are
applied to ``os.environ`` immediately so settings that are read at call time
take effect without a restart; fields marked ``restart`` are only re-read when
the sidecar starts.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ASSIGN_RE = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")
_SECRET_HINT = re.compile(
    r"(^|_)(API_KEY|KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL)($|_)",
    re.I,
)


@dataclass(frozen=True)
class EnvField:
    key: str
    label: str
    description: str = ""
    kind: str = "text"  # text | number | boolean | select
    choices: tuple[str, ...] = ()
    restart: bool = False


@dataclass(frozen=True)
class EnvGroup:
    id: str
    label: str
    description: str
    fields: tuple[EnvField, ...]


ENV_GROUPS: tuple[EnvGroup, ...] = (
    EnvGroup(
        "brain",
        "AI brain",
        "Provider keys and model selection. Saving a key rebuilds the brain.",
        (
            EnvField("NEBIUS_API_KEY", "Nebius API key", "Token Factory key.", restart=False),
            EnvField("OPENROUTER_API_KEY", "OpenRouter API key", "Optional fallback key."),
            EnvField(
                "WINBROW_BRAIN_PROVIDER",
                "Provider",
                "auto, nebius, openrouter, openai or local.",
                kind="select",
                choices=("auto", "nebius", "openrouter", "openai", "local"),
            ),
            EnvField("WINBROW_BRAIN_MODEL", "Default model", "OpenRouter model id."),
            EnvField("WINBROW_NEBIUS_MODEL", "Nebius model", "Token Factory model id."),
            EnvField("WINBROW_NEBIUS_BASE", "Nebius base URL", "OpenAI-compatible base."),
            EnvField("WINBROW_BRAIN_TIMEOUT", "Request timeout (s)", kind="number"),
            EnvField("WINBROW_BRAIN_DEADLINE_S", "Task deadline (s)", "0 disables.", kind="number"),
            EnvField("WINBROW_STREAM", "Stream responses", "0 forces buffered calls.", kind="boolean"),
            EnvField(
                "WINBROW_OPENROUTER_PROVIDER",
                "OpenRouter upstream provider",
                "Empty lets OpenRouter choose.",
            ),
            EnvField(
                "WINBROW_OPENROUTER_ALLOW_FALLBACKS",
                "Allow OpenRouter fallbacks",
                kind="boolean",
            ),
            EnvField("WINBROW_REASONING_RETRY_TOKENS", "Empty-content retry cap", kind="number"),
            EnvField("WINBROW_REASONING_OFF_MAX_TOKENS", "Reasoning-off max tokens", kind="number"),
        ),
    ),
    EnvGroup(
        "agent",
        "Agent behaviour",
        "Action budget, approvals and planning.",
        (
            EnvField("WINBROW_BRAIN_FIRST", "Brain first", "0 only for legacy debugging.", kind="boolean"),
            EnvField("WINBROW_MAX_STEPS", "Max steps per task", kind="number"),
            EnvField("WINBROW_STEP_WARN", "Warn N steps before limit", kind="number"),
            EnvField("WINBROW_MAX_ACTIONS_PER_TURN", "Max actions per turn", "1-10.", kind="number"),
            EnvField("WINBROW_PARALLEL_READS", "Parallel read-only steps", kind="boolean"),
            EnvField("WINBROW_AUTO_APPROVE_T2", "Auto-approve Tier 2", "File writes and commands.", kind="boolean"),
            EnvField("WINBROW_BYPASS_CONFIRM", "Bypass all confirmations", "Dangerous.", kind="boolean"),
            EnvField("WINBROW_SUBAGENTS", "Enable subagents", kind="boolean"),
            EnvField(
                "WINBROW_SUBAGENTS_EXPLICIT",
                "Only on explicit request",
                "1 requires the user to ask for subagents.",
                kind="boolean",
            ),
            EnvField("WINBROW_SUBAGENT_PARALLEL", "Subagent parallel limit", kind="number"),
            EnvField("WINBROW_NOVELTY_NUDGE", "Novelty nudge", kind="boolean"),
        ),
    ),
    EnvGroup(
        "voice",
        "Voice",
        "Local VAD / wake / push-to-talk. Changes need a sidecar restart.",
        (
            EnvField("WINBROW_VOICE", "Voice on boot", kind="boolean", restart=True),
            EnvField("WINBROW_VOICE_MODE", "Loop mode", "vad or ptt.", restart=True),
            EnvField("WINBROW_PARTIAL_STT", "Live partial transcripts", kind="boolean", restart=True),
        ),
    ),
    EnvGroup(
        "search",
        "Files & search",
        "Everything indexing, image folders and web search.",
        (
            EnvField("WINBROW_EVERYTHING_AUTOINSTALL", "Auto-install Everything", kind="boolean", restart=True),
            EnvField("WINBROW_EVERYTHING_DIR", "Everything install folder", restart=True),
            EnvField("WINBROW_EVERYTHING_FOLDERS", "Indexed folders", "Semicolon-separated.", restart=True),
            EnvField("WINBROW_SEARCH_TIMEOUT", "Web search timeout (s)", kind="number"),
            EnvField("WINBROW_TLS_IMPERSONATE", "TLS fingerprints", "Comma-separated."),
            EnvField("WINBROW_FETCH_FOCUS_CHARS", "Focused fetch limit", kind="number"),
            EnvField("WINBROW_WALLPAPER_QUERY", "Default wallpaper subject"),
            EnvField("WINBROW_WALLPAPER_MIN", "Minimum wallpaper size", "e.g. 1600x900."),
            EnvField("WINBROW_WALLPAPER_DIR", "Wallpaper folder"),
            EnvField("WINBROW_IMAGE_DIR", "Image download folder"),
            EnvField("WINBROW_IMAGE_UA", "Image user agent"),
            EnvField(
                "WINBROW_WALLPAPER_KEEP_STYLE",
                "Keep wallpaper fit style",
                "0 forces Fill.",
                kind="boolean",
            ),
            EnvField(
                "WINBROW_ARTIFACT_DIRS",
                "Extra artifact folders",
                "os.pathsep separated.",
            ),
        ),
    ),
    EnvGroup(
        "local",
        "Local model",
        "Only used when the provider is local/qwen. Changes need a restart.",
        (
            EnvField("WINBROW_LOCAL_LLM", "Use built-in local model", kind="boolean", restart=True),
            EnvField(
                "WINBROW_LOCAL_LLM_ENDPOINT",
                "External endpoint",
                "OpenAI-compatible server; leave blank for the built-in llama.cpp server.",
                restart=True,
            ),
            EnvField(
                "WINBROW_LOCAL_LLM_MODEL",
                "External model name",
                "Required when an external endpoint is set.",
                restart=True,
            ),
            EnvField("WINBROW_LOCAL_LLM_CTX", "Context size", kind="number", restart=True),
            EnvField("WINBROW_LOCAL_LLM_THREADS", "Threads", kind="number", restart=True),
            EnvField("WINBROW_LOCAL_LLM_TIMEOUT", "Request timeout (s)", kind="number", restart=True),
        ),
    ),
    EnvGroup(
        "advanced",
        "Advanced",
        "History budgets, reasoning and retention.",
        (
            EnvField(
                "WINBROW_CONTEXT_TOKENS",
                "Provider context tokens",
                "0 = auto: 25% of the window, 240k-char interim.",
                kind="number",
            ),
            EnvField("WINBROW_HISTORY_MAX_CHARS", "History character budget", kind="number"),
            EnvField("WINBROW_HISTORY_FULL", "Full-fidelity history", kind="boolean"),
            EnvField("WINBROW_SESSION_CONTEXT_MIN", "Session context minutes", kind="number"),
            EnvField("WINBROW_STEP_OUTPUT_CHARS", "Step output cap", "0 = no limit.", kind="number"),
            EnvField(
                "WINBROW_ARTIFACT_CONTEXT_MIN",
                "Artifact context minutes",
                "0 = never expire.",
                kind="number",
            ),
            EnvField(
                "WINBROW_HISTORY_BROWSER_FIRST",
                "Evict browser snapshots first",
                kind="boolean",
            ),
            EnvField("WINBROW_REASONING_MAX_TOKENS", "Reasoning token cap", kind="number"),
            EnvField(
                "WINBROW_NEBIUS_REASONING_EFFORT",
                "Nebius reasoning effort",
                kind="select",
                choices=("low", "medium", "high", "none"),
            ),
            EnvField("WINBROW_PLANNER_MAX_TOKENS", "Planner max tokens", kind="number"),
            EnvField("WINBROW_PLANNER_TEMPERATURE", "Planner temperature", kind="number"),
            EnvField("WINBROW_TASKS_RETENTION_DAYS", "Task retention (days)", kind="number"),
            EnvField("WINBROW_RESULTS_RETENTION_DAYS", "Result log retention (days)", kind="number"),
            EnvField(
                "WINBROW_TASKS_DB",
                "Task database path",
                "Default data/tasks.db.",
                restart=True,
            ),
        ),
    ),
)


def _catalog_fields() -> dict[str, EnvField]:
    return {field.key: field for group in ENV_GROUPS for field in group.fields}


def _computed_defaults() -> dict[str, str]:
    """Paths and machine values that are derived rather than fixed strings."""
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    local = Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local")
    drives = ""
    try:
        from .everything import _fixed_drive_roots

        drives = ";".join(_fixed_drive_roots())
    except Exception:
        drives = ""
    return {
        "WINBROW_EVERYTHING_DIR": str(local / "WinBrow" / "Everything"),
        "WINBROW_EVERYTHING_FOLDERS": drives,
        "WINBROW_WALLPAPER_DIR": str(home / "Pictures" / "WinBrow Wallpapers"),
        "WINBROW_IMAGE_DIR": str(home / "Pictures" / "WinBrow Images"),
        "WINBROW_LOCAL_LLM_THREADS": str(os.cpu_count() or ""),
    }


def _defaults() -> dict[str, str]:
    merged = dict(DEFAULTS)
    merged.update(_computed_defaults())
    return merged


# Effective defaults when a variable is absent from .env and the process
# environment. These mirror the code defaults (and .env.example where the code
# has no fallback). The Settings tab shows them as the starting value.
DEFAULTS: dict[str, str] = {
    # Brain
    "WINBROW_BRAIN_PROVIDER": "auto",
    "WINBROW_BRAIN_MODEL": "deepseek/deepseek-v4.1-flash",
    "WINBROW_NEBIUS_MODEL": "deepseek-ai/DeepSeek-V4-Flash-0731",
    "WINBROW_NEBIUS_BASE": "https://api.tokenfactory.nebius.com/v1",
    "WINBROW_BRAIN_TIMEOUT": "45",
    "WINBROW_BRAIN_DEADLINE_S": "300",
    "WINBROW_STREAM": "1",
    "WINBROW_OPENROUTER_PROVIDER": "relace",
    "WINBROW_OPENROUTER_ALLOW_FALLBACKS": "0",
    "WINBROW_REASONING_RETRY_TOKENS": "400",
    "WINBROW_REASONING_OFF_MAX_TOKENS": "1000",
    # Agent behaviour
    "WINBROW_BRAIN_FIRST": "1",
    "WINBROW_MAX_STEPS": "20",
    "WINBROW_STEP_WARN": "5",
    "WINBROW_MAX_ACTIONS_PER_TURN": "5",
    "WINBROW_PARALLEL_READS": "0",
    "WINBROW_AUTO_APPROVE_T2": "0",
    "WINBROW_BYPASS_CONFIRM": "0",
    "WINBROW_SUBAGENTS": "1",
    "WINBROW_SUBAGENTS_EXPLICIT": "0",
    "WINBROW_SUBAGENT_PARALLEL": "3",
    "WINBROW_NOVELTY_NUDGE": "1",
    # Voice
    "WINBROW_VOICE": "0",
    "WINBROW_VOICE_MODE": "ptt",
    "WINBROW_PARTIAL_STT": "1",
    # Files & search
    "WINBROW_EVERYTHING_AUTOINSTALL": "1",
    "WINBROW_SEARCH_TIMEOUT": "20",
    "WINBROW_TLS_IMPERSONATE": "chrome124,safari17_0",
    "WINBROW_FETCH_FOCUS_CHARS": "6000",
    "WINBROW_WALLPAPER_QUERY": "anime",
    "WINBROW_WALLPAPER_MIN": "1600x900",
    "WINBROW_WALLPAPER_KEEP_STYLE": "0",
    # Local model
    "WINBROW_LOCAL_LLM": "0",
    "WINBROW_LOCAL_LLM_CTX": "8192",
    "WINBROW_LOCAL_LLM_TIMEOUT": "300",
    # Advanced
    "WINBROW_CONTEXT_TOKENS": "0",
    "WINBROW_HISTORY_MAX_CHARS": "240000",
    "WINBROW_HISTORY_FULL": "1",
    "WINBROW_HISTORY_BROWSER_FIRST": "1",
    "WINBROW_STEP_OUTPUT_CHARS": "4000",
    "WINBROW_ARTIFACT_CONTEXT_MIN": "120",
    "WINBROW_SESSION_CONTEXT_MIN": "720",
    "WINBROW_REASONING_MAX_TOKENS": "2000",
    "WINBROW_NEBIUS_REASONING_EFFORT": "low",
    "WINBROW_PLANNER_MAX_TOKENS": "16000",
    "WINBROW_PLANNER_TEMPERATURE": "1",
    "WINBROW_TASKS_RETENTION_DAYS": "30",
    "WINBROW_RESULTS_RETENTION_DAYS": "7",
    "WINBROW_TASKS_DB": "data/tasks.db",
}


def _restart_keys() -> set[str]:
    return {field.key for field in _catalog_fields().values() if field.restart}


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def parse_env_file(path: Optional[Path] = None) -> dict[str, str]:
    """Read active KEY=value assignments from ``.env`` (comments skipped)."""
    target = path or ENV_PATH
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return {}
    except OSError:
        return {}
    values: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        match = _ASSIGN_RE.match(line)
        if not match:
            continue
        values[match.group(2)] = _strip_quotes(match.group(3))
    return values


def _encode_value(value: str) -> str:
    value = str(value).replace("\r", " ").replace("\n", " ").strip()
    if not value:
        return ""
    # Quote values that would otherwise be parsed as a comment or split.
    if re.search(r"\s|#", value) and '"' not in value:
        return f'"{value}"'
    return value


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def _is_secret(key: str, field: Optional[EnvField] = None) -> bool:
    if field is not None and field.key in {"NEBIUS_API_KEY", "OPENROUTER_API_KEY"}:
        return True
    return bool(_SECRET_HINT.search(key))


def _truthy(value: str) -> bool:
    return value.strip().lower() not in {"", "0", "false", "no", "off"}


def _field_view(
    field: EnvField,
    values: dict[str, str],
    sources: dict[str, str],
    in_file: set[str],
    defaults: dict[str, str],
) -> dict[str, Any]:
    raw = values.get(field.key, "")
    default = defaults.get(field.key, "")
    secret = _is_secret(field.key, field)
    return {
        "key": field.key,
        "label": field.label,
        "description": field.description,
        "kind": field.kind,
        "choices": list(field.choices),
        "restart": field.restart,
        "secret": secret,
        "value": "" if secret else raw,
        "default": "" if secret else default,
        "source": sources.get(field.key, "default"),
        "is_set": bool(raw.strip()),
        "in_file": field.key in in_file,
    }


def describe_env(path: Optional[Path] = None) -> dict[str, Any]:
    """Return grouped fields with effective values, defaults and their source."""
    target = path or ENV_PATH
    file_values = parse_env_file(target)
    in_file = set(file_values)
    catalog = _catalog_fields()
    defaults = _defaults()

    values: dict[str, str] = {}
    sources: dict[str, str] = {}
    for key in catalog:
        if key in file_values:
            values[key] = file_values[key]
            sources[key] = "env"
        elif key in os.environ:
            values[key] = os.environ[key]
            sources[key] = "process"
        else:
            values[key] = defaults.get(key, "")
            sources[key] = "default"

    groups: list[dict[str, Any]] = []
    for group in ENV_GROUPS:
        fields = [
            _field_view(field, values, sources, in_file, defaults)
            for field in group.fields
        ]
        groups.append({
            "id": group.id,
            "label": group.label,
            "description": group.description,
            "fields": fields,
        })

    custom: list[dict[str, Any]] = []
    for key in sorted(in_file):
        if key in catalog:
            continue
        raw = file_values[key]
        secret = _is_secret(key)
        custom.append({
            "key": key,
            "label": key,
            "description": "Custom variable from .env",
            "kind": "text",
            "choices": [],
            "restart": False,
            "secret": secret,
            "value": "" if secret else raw,
            "default": "",
            "source": "env",
            "is_set": bool(raw.strip()),
            "in_file": True,
        })

    return {
        "path": str(target),
        "groups": groups,
        "custom": custom,
        "secrets_stored_plaintext": True,
    }


def save_env(
    updates: dict[str, str],
    unset: Iterable[str] = (),
    path: Optional[Path] = None,
) -> dict[str, Any]:
    """Merge updates into ``.env``, persist atomically and apply to os.environ."""
    target = path or ENV_PATH
    normalized: dict[str, str] = {}
    for raw_key, raw_value in (updates or {}).items():
        key = str(raw_key).strip()
        if not _KEY_RE.match(key):
            raise ValueError(f"Invalid environment variable name: {raw_key!r}")
        normalized[key] = str(raw_value)

    drop = set()
    for raw_key in unset or ():
        key = str(raw_key).strip()
        if not _KEY_RE.match(key):
            raise ValueError(f"Invalid environment variable name: {raw_key!r}")
        drop.add(key)

    for key, value in list(normalized.items()):
        if key in drop:
            normalized.pop(key)
            continue
        if _is_secret(key) and not value.strip():
            normalized.pop(key)
            drop.add(key)

    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        lines = [
            "# WinBrow environment — edited from the in-app Settings tab.",
            "",
        ]
    except OSError:
        lines = []

    pending = dict(normalized)
    output: list[str] = []
    for line in lines:
        match = _ASSIGN_RE.match(line)
        if not match:
            output.append(line)
            continue
        key = match.group(2)
        if key in drop:
            continue
        if key in pending:
            output.append(f"{key}={_encode_value(pending.pop(key))}")
        else:
            output.append(line)

    if pending:
        if output and output[-1].strip():
            output.append("")
        for key, value in pending.items():
            output.append(f"{key}={_encode_value(value)}")

    _atomic_write(target, "\n".join(output).rstrip() + "\n")

    for key, value in normalized.items():
        os.environ[key] = value
    for key in drop:
        os.environ.pop(key, None)

    restart_keys = _restart_keys()
    changed = set(normalized) | drop
    return {
        "status": "saved",
        "path": str(target),
        "saved": sorted(normalized),
        "unset": sorted(drop),
        "requires_restart": bool(changed & restart_keys),
        "restart_keys": sorted(changed & restart_keys),
    }
