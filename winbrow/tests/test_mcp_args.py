"""MCP inputSchema -> ArgSpec mapping keeps optionality.

The planner must be able to omit an optional MCP argument that has no JSON
schema default; otherwise every arxiv/open-meteo call is rejected preflight.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from winbrow.mcp import _schema_args, _schema_argspec  # noqa: E402


def test_schema_args_preserves_required_flag():
    schema = {
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer"},
        },
        "required": ["query"],
    }
    args = dict(_schema_args(schema))
    assert args["query"]["required"] is True
    assert args["max_results"]["required"] is False


def test_optional_schema_argument_is_not_required_by_preflight():
    spec = _schema_argspec(
        "max_results", {"type": "integer"}, False,
    )
    assert spec.default is None
    assert spec.required is False


def test_required_schema_argument_stays_required():
    spec = _schema_argspec("query", {"type": "string"}, True)
    assert spec.required is True


def test_array_schema_argument_is_json_not_scalar_text():
    spec = _schema_argspec(
        "excludePatterns", {"type": "array", "items": {"type": "string"}}, False,
    )
    assert spec.kind == "json"
    assert spec.required is False
