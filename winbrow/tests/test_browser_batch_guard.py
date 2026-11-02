"""Batch identity observations with mocked CDP and (optionally) a Node DOM stub."""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from winbrow.browser_task import BrowserController

AGENT = {"id": "agent-tab", "url": "https://example.test/stale-listing"}
USER = {"id": "user-tab", "url": "https://personal.test/"}
URL = "https://example.test/form"


def signature(**changes):
    return {
        "exists": True,
        "count": 1,
        "tag": "input",
        "type": "checkbox",
        "id": "control",
        "name": "option",
        "role": "",
        "href": "",
        "label": "Account option",
        "disabled": False,
        "connected": True,
        "visible": True,
        **changes,
    }


def snapshot(selectors=()):
    return {
        "identity": {"url": URL, "document_id": "backend-document-token"},
        "targets": {selector: signature() for selector in selectors},
    }


def response(state):
    return {"result": {"result": {"type": "object", "value": state}}}


class MockBrowserController(BrowserController):
    connection: Mock
    connected_tabs: list[dict]


@pytest.fixture
def controller():
    browser = MockBrowserController()
    browser._agent_tab_id = AGENT["id"]
    browser._current_tab_id = USER["id"]
    browser._list_tabs = AsyncMock(return_value=[USER, AGENT])
    browser._pick_tab = Mock(side_effect=AssertionError("must not reselect a tab"))
    browser.execute_js = AsyncMock(side_effect=AssertionError("must pin the exact tab"))
    browser.connection = Mock()
    browser.connection.call = AsyncMock(return_value=response(snapshot()))
    browser.connected_tabs = []

    @asynccontextmanager
    async def page_conn(tab):
        browser.connected_tabs.append(tab)
        yield browser.connection

    browser._page_conn = page_conn
    # No lifecycle, foreground, clipboard, navigation, or cached-state fallback.
    for name in (
        "get_or_create_agent_tab",
        "_open_new_tab",
        "_open_tab",
        "_activate_tab",
        "ensure_browser_with_cdp",
        "ensure_browser_open",
        "get_current_url",
        "get_page_state",
        "read_page_text",
        "navigate_to",
        "new_tab",
    ):
        setattr(
            browser, name, AsyncMock(side_effect=AssertionError(f"unexpected {name}"))
        )
    yield browser
    for name in (
        "get_or_create_agent_tab",
        "_open_new_tab",
        "_open_tab",
        "_activate_tab",
        "ensure_browser_with_cdp",
        "ensure_browser_open",
        "get_current_url",
        "get_page_state",
        "read_page_text",
        "navigate_to",
        "new_tab",
        "execute_js",
    ):
        getattr(browser, name).assert_not_called()
    browser._pick_tab.assert_not_called()


def capture(browser, selectors=None):
    return asyncio.run(browser.batch_state(selectors))


def assert_closed(result):
    assert result["success"] is False
    assert result["error"]
    assert set(result["identity"]) == {"tab_id", "url", "document_id"}
    assert result["identity"]["url"] is None
    assert result["identity"]["document_id"] is None
    assert result["targets"] == {}


@pytest.mark.parametrize("tab_id", [None, ""])
def test_no_agent_tab_never_reads_or_hijacks_current_tab(controller, tab_id):
    controller._agent_tab_id = tab_id
    assert_closed(capture(controller, ["#control"]))
    controller._list_tabs.assert_not_called()
    controller.connection.call.assert_not_called()
    assert controller.connected_tabs == []
    assert controller._current_tab_id == USER["id"]


@pytest.mark.parametrize("tabs", [[], [USER]])
def test_missing_agent_or_cdp_does_not_create_or_hijack(controller, tabs):
    controller._list_tabs.return_value = tabs
    assert_closed(capture(controller))
    controller.connection.call.assert_not_called()
    assert controller.connected_tabs == []
    assert controller._agent_tab_id == AGENT["id"]


def test_identity_shape_and_exact_tab_not_current_or_first_tab(controller):
    expected = snapshot(["#control"])
    controller.connection.call.return_value = response(expected)
    result = capture(controller, ["#control"])
    assert result == {
        "success": True,
        "identity": {"tab_id": AGENT["id"], **expected["identity"]},
        "targets": expected["targets"],
    }
    assert result["identity"]["url"] != AGENT["url"]  # location.href, not tab metadata
    assert controller.connected_tabs == [AGENT]
    assert controller._current_tab_id == USER["id"]
    args, kwargs = controller.connection.call.call_args
    assert args[0] == "Runtime.evaluate"
    assert args[1]["returnByValue"] is True
    assert kwargs == {"timeout": 8}


@pytest.mark.parametrize("selectors", [None, []])
def test_identity_only_snapshot(controller, selectors):
    result = capture(controller, selectors)
    assert result["success"] is True
    assert result["targets"] == {}


def test_selectors_are_json_encoded_without_modifying_the_callers_list(controller):
    selectors = [
        '[data-name="a\\b\'c"]',
        '"); globalThis.injected = true; //\n\u2028',
        "__proto__",
    ]
    original = selectors.copy()
    controller.connection.call.return_value = response(snapshot(selectors))
    assert capture(controller, selectors)["success"] is True
    code = controller.connection.call.call_args.args[1]["expression"]
    assert f"({json.dumps(selectors)}, " in code
    assert selectors == original


@pytest.mark.parametrize("selectors", ["#control", {}, [None], [1]])
def test_invalid_selector_arguments_fail_closed(controller, selectors):
    assert_closed(capture(controller, selectors))
    controller._list_tabs.assert_not_called()


@pytest.mark.parametrize(
    "phase", ["listing", "connecting", "evaluating", "after_capture"]
)
@pytest.mark.parametrize("replacement", [None, "different-agent-tab"])
def test_session_change_at_await_boundaries_fails_closed(
    controller, phase, replacement
):
    if phase == "listing":

        async def listing():
            controller._agent_tab_id = replacement
            return [USER, AGENT]

        controller._list_tabs.side_effect = listing
    elif phase == "connecting":

        @asynccontextmanager
        async def connecting(tab):
            assert tab == AGENT
            controller._agent_tab_id = replacement
            yield controller.connection

        controller._page_conn = connecting
    elif phase == "evaluating":

        async def evaluating(*args, **kwargs):
            controller._agent_tab_id = replacement
            return response(snapshot())

        controller.connection.call.side_effect = evaluating
    else:

        async def listing():
            if controller._list_tabs.await_count == 2:
                controller._agent_tab_id = replacement
            return [USER, AGENT]

        controller._list_tabs.side_effect = listing
    assert_closed(capture(controller))
    if phase in ("listing", "connecting"):
        controller.connection.call.assert_not_called()
    assert all(tab == AGENT for tab in controller.connected_tabs)


def test_tab_closed_after_evaluation_fails_closed(controller):
    controller._list_tabs.side_effect = [[USER, AGENT], [USER]]
    assert_closed(capture(controller))


@pytest.mark.parametrize("phase", ["listing", "connecting", "evaluating"])
def test_transport_exceptions_fail_closed(controller, phase):
    if phase == "listing":
        controller._list_tabs.side_effect = RuntimeError("no CDP")
    elif phase == "connecting":

        @asynccontextmanager
        async def disconnected(tab):
            raise RuntimeError("CDP not available")
            yield  # pragma: no cover

        controller._page_conn = disconnected
    else:
        controller.connection.call.side_effect = TimeoutError("evaluation timed out")
    assert_closed(capture(controller))


@pytest.mark.parametrize(
    "reply",
    [
        {"error": {"message": "target closed"}},
        {"result": {"exceptionDetails": {"text": "invalid selector"}}},
        {"result": {"result": {"type": "undefined"}}},
        response(None),
        response("not an object"),
        response({}),
        response({"identity": {"url": URL}, "targets": {}}),
        response({"identity": {"url": URL, "document_id": ""}, "targets": {}}),
        response({"identity": {"url": "", "document_id": "token"}, "targets": {}}),
        response({"identity": {"url": URL, "document_id": "token"}, "targets": []}),
    ],
)
def test_uncapturable_or_incomplete_state_fails_closed(controller, reply):
    controller.connection.call.return_value = reply
    assert_closed(capture(controller))


@pytest.mark.parametrize(
    "target",
    [
        None,
        {},
        signature(count=True),
        signature(count=-1),
        signature(exists=False),
        signature(visible=None),
        signature(tag=""),
    ],
)
def test_incomplete_target_signatures_fail_closed(controller, target):
    state = snapshot(["#control"])
    state["targets"]["#control"] = target
    controller.connection.call.return_value = response(state)
    assert_closed(capture(controller, ["#control"]))


def test_missing_requested_target_snapshot_fails_closed(controller):
    assert_closed(capture(controller, ["#control"]))


# Run the actual injected expression against a tiny DOM stub, never a browser.
# Node is optional so the pure mocked-CDP tests still run on Python-only installs.
DOM_STUB = r"""
const vm = require('node:vm');
const input = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const queries = [];
let attrs, el, style;
function freshDocument() {
    attrs = {name: 'option', type: 'checkbox', ...(input.attrs || {})};
    style = {display: 'block', visibility: 'visible', opacity: '1'};
    el = {
        tagName: 'INPUT', id: 'control', type: 'checkbox', labels: [{textContent: 'Account option'}],
        textContent: '', isConnected: true, isContentEditable: false,
        checked: false, value: '', disabled: false,
        getAttribute(name) { return attrs[name] ?? null; },
        matches(selector) { return selector === ':disabled' && this.disabled; },
        getClientRects() { return [{width: 20, height: 20}]; }
    };
    return {
        getElementById(id) { return id === 'label-id' ? {textContent: 'External label'} : null; },
        querySelectorAll(selector) {
            queries.push(selector);
            if (selector === '[') throw new SyntaxError('invalid selector');
            if (selector === '#missing') return [];
            if (selector === '.many') return [el, {...el}];
            return [el];
        }
    };
}
const context = {document: freshDocument(), location: {href: input.url},
    window: {getComputedStyle() { return style; }}};
vm.createContext(context);
const states = [], errors = [];
input.expressions.forEach((expression, i) => {
    switch ((input.changes || [])[i]) {
        case 'edit':
            el.checked = true; el.value = 'expected new value'; el.textContent = 'typed text';
            context.document.unrelatedDomMutation = 'not a navigation barrier'; break;
        case 'reload': context.document = freshDocument(); break;
        case 'navigate': context.location.href += '?changed'; break;
        case 'disable': el.disabled = true; break;
        case 'hide': style.display = 'none'; break;
        case 'disconnect': el.isConnected = false; break;
        case 'relabel': attrs['aria-label'] = 'Different action'; break;
    }
    try { states.push(vm.runInContext(expression, context, {timeout: 1000})); }
    catch (error) { errors.push(String(error)); }
});
const token = Object.getOwnPropertyDescriptor(context.document, '__winbrowBatchDocumentId');
console.log(JSON.stringify({states, errors, queries, injected: !!context.injected,
    tokenEnumerable: token && token.enumerable, tokenWritable: token && token.writable}));
"""


@pytest.fixture
def run_dom():
    node = shutil.which("node")
    if not node:
        pytest.skip("optional Node runtime needed to execute the mocked DOM expression")

    def execute(expressions, **options):
        completed = subprocess.run(
            [node, "-e", DOM_STUB],
            input=json.dumps({"expressions": expressions, "url": URL, **options}),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=True,
        )
        return json.loads(completed.stdout)

    return execute


def expressions(controller, selectors, count=1):
    controller.connection.call.return_value = response(snapshot(selectors))
    codes = []
    for _ in range(count):
        assert capture(controller, selectors)["success"] is True
        codes.append(controller.connection.call.call_args.args[1]["expression"])
    return codes


def test_actual_js_identity_survives_edits_but_detects_same_url_reload(
    controller, run_dom
):
    codes = expressions(controller, ["#control"], 3)
    assert codes[0] != codes[1]  # a fresh backend random token candidate per capture
    result = run_dom(codes, changes=[None, "edit", "reload"])
    assert result["errors"] == []
    before, edited, reloaded = result["states"]
    assert before == edited  # includes value/checked changes and unrelated DOM edits
    assert before["identity"]["url"] == reloaded["identity"]["url"] == URL
    assert before["identity"]["document_id"] != reloaded["identity"]["document_id"]
    assert len(before["identity"]["document_id"]) == 32
    assert result["tokenEnumerable"] is False
    assert result["tokenWritable"] is False
    assert before["targets"]["#control"] == signature()
    assert "checked" not in before["targets"]["#control"]
    assert "value" not in before["targets"]["#control"]


@pytest.mark.parametrize(
    "change, field, expected",
    [
        ("disable", "disabled", True),
        ("hide", "visible", False),
        ("disconnect", "connected", False),
        ("relabel", "label", "Different action"),
    ],
)
def test_actual_js_tracks_relevant_target_changes(
    controller, run_dom, change, field, expected
):
    result = run_dom(expressions(controller, ["#control"], 2), changes=[None, change])
    assert result["errors"] == []
    before, after = result["states"]
    assert before["identity"] == after["identity"]
    assert before["targets"] != after["targets"]
    assert after["targets"]["#control"][field] == expected


def test_actual_js_tracks_url_change_without_replacing_document(controller, run_dom):
    result = run_dom(expressions(controller, [], 2), changes=[None, "navigate"])
    before, after = result["states"]
    assert before["identity"]["url"] != after["identity"]["url"]
    assert before["identity"]["document_id"] == after["identity"]["document_id"]


def test_actual_js_selector_escaping_counts_and_missing_targets(controller, run_dom):
    selectors = [
        "#control",
        "#missing",
        ".many",
        "__proto__",
        '"); injected = true; //\n\\\u2028',
        '[aria-label="O\'Reilly"]',
    ]
    result = run_dom(expressions(controller, selectors))
    assert result["errors"] == []
    assert result["queries"] == selectors
    assert not result["injected"]
    targets = result["states"][0]["targets"]
    assert set(targets) == set(selectors)
    assert targets["__proto__"] == signature()
    assert targets[".many"]["count"] == 2
    assert targets["#missing"] == signature(
        exists=False,
        count=0,
        tag="",
        type="",
        id="",
        name="",
        label="",
        disabled=False,
        connected=False,
        visible=False,
    )


@pytest.mark.parametrize(
    "attrs, label, disabled",
    [
        ({"aria-label": "  Accessible   name "}, "Accessible name", False),
        (
            {"aria-labelledby": "label-id", "aria-label": "lower priority"},
            "External label",
            False,
        ),
        ({"aria-disabled": "true"}, "Account option", True),
    ],
)
def test_actual_js_accessible_label_and_aria_disabled(
    controller, run_dom, attrs, label, disabled
):
    result = run_dom(expressions(controller, ["#control"]), attrs=attrs)
    target = result["states"][0]["targets"]["#control"]
    assert target["label"] == label
    assert target["disabled"] is disabled


def test_actual_js_invalid_selector_is_not_a_successful_missing_target(
    controller, run_dom
):
    result = run_dom(expressions(controller, ["["]))
    assert result["states"] == []
    assert "invalid selector" in result["errors"][0]
