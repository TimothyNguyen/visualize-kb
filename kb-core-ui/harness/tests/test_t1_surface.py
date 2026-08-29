from __future__ import annotations

from pathlib import Path

import pytest
from conftest import FIXTURES_DIR

from harness.engines import get_engine
from harness.manifest import discover_fixtures
from harness.modes.parity import _run_engine_ops
from harness.runner import ProcessRunner


def _run_fixture(fixtures_dir: Path, go_bin: str, tmp_path: Path, fixture_name: str) -> dict:
    engine = get_engine("go", bin_override=go_bin)
    fixture = next(f for f in discover_fixtures(fixtures_dir) if f.name == fixture_name)
    runner = ProcessRunner(engine, tmp_path / "work")
    return _run_engine_ops(runner, fixture, engine, "t1-surface-test", keep_work_dir=False)


@pytest.fixture(scope="module")
def cli_results(go_bin, tmp_path_factory) -> dict:
    return _run_fixture(FIXTURES_DIR, go_bin, tmp_path_factory.mktemp("cli"), "cli-surface")


@pytest.fixture(scope="module")
def rest_results(go_bin, tmp_path_factory) -> dict:
    return _run_fixture(FIXTURES_DIR, go_bin, tmp_path_factory.mktemp("rest"), "rest-errors")


@pytest.fixture(scope="module")
def mcp_results(go_bin, tmp_path_factory) -> dict:
    return _run_fixture(FIXTURES_DIR, go_bin, tmp_path_factory.mktemp("mcp"), "mcp-surface")


def test_help_goes_to_stdout_and_exits_zero(cli_results: dict):
    help_root = cli_results["help-root"]
    assert help_root["exit_code"] == 0
    assert "Available Commands:" in help_root["stdout"]
    assert help_root["stderr"] == ""
    assert cli_results["no-args"] == help_root


def test_help_text_is_utf8_not_locale_mangled(cli_results: dict):
    assert "—" in cli_results["help-root"]["stdout"]
    assert "â€" not in cli_results["help-root"]["stdout"]


@pytest.mark.parametrize(
    "op_id,needle",
    [
        ("unknown-command", 'unknown command "bogus"'),
        ("parse-too-many-args", "accepts at most 1 arg(s), received 2"),
        ("memory-add-no-title", "--title is required"),
        ("memory-rm-absent", 'no memory with id "no-such-id"'),
    ],
)
def test_cli_errors_go_to_stderr_with_exit_one(cli_results: dict, op_id: str, needle: str):
    result = cli_results[op_id]
    assert result["exit_code"] == 1
    assert result["stdout"] == ""
    assert needle in result["stderr"]


def test_parse_missing_repo_exits_one(cli_results: dict):
    # stderr is ignore_fields'd in the manifest: it embeds an OS-level stat
    # message that no reimplementation can reproduce byte-for-byte.
    assert cli_results["parse-missing-repo"]["exit_code"] == 1


@pytest.mark.parametrize(
    "op_id,status,message",
    [
        ("symbol-not-found", 404, "symbol not found: nope"),
        ("subgraph-missing-symbol", 400, "missing symbol query param"),
        ("subgraph-invalid-depth", 400, "invalid depth"),
        ("subgraph-symbol-not-found", 404, "symbol not found: nope"),
        ("source-missing-file", 400, "missing file query param"),
        ("source-invalid-range", 400, "invalid start/end"),
        ("source-escape-root", 400, "file path escapes repo root"),
        ("source-file-not-found", 404, "file not found: nope.go"),
        ("memory-invalid-kind", 400, "invalid kind"),
        ("memory-add-malformed-json", 400, "invalid JSON body"),
        ("memory-add-missing-title", 400, "title and text are required"),
        ("memory-add-invalid-kind", 400, "invalid kind (want: rule, lesson, business, overview, reference)"),
        ("memory-delete-absent", 404, "no memory with id no-such-id"),
    ],
)
def test_rest_errors_use_the_shared_error_envelope(
    rest_results: dict, op_id: str, status: int, message: str
):
    result = rest_results[op_id]
    assert result["status"] == status
    assert result["body"] == {"error": message}


def test_api_mux_not_found_is_plain_text(rest_results: dict):
    result = rest_results["api-mux-not-found"]
    assert result["status"] == 404
    assert result["text_body"].strip() == "404 page not found"


def test_unknown_file_symbols_is_empty_list_not_error(rest_results: dict):
    assert rest_results["file-symbols-unknown-file"] == {"status": 200, "body": []}


def test_tools_list_exposes_graph_and_memory_tools(mcp_results: dict):
    tools = {t["name"]: t for t in mcp_results["tools-list"]["result"]["tools"]}
    assert set(tools) == {
        "search_symbol",
        "get_symbol",
        "get_file_symbols",
        "get_callees",
        "get_callers",
        "get_file_slice",
        "get_tree",
        "get_stats",
        "memory_search",
        "memory_add",
    }
    assert tools["get_symbol"]["inputSchema"]["required"] == ["id"]
    assert set(tools["get_file_slice"]["inputSchema"]["required"]) == {"file", "start", "end"}
    assert set(tools["memory_add"]["inputSchema"]["required"]) == {"kind", "title", "text"}
    assert all(t["description"] for t in tools.values())


@pytest.mark.parametrize(
    "op_id,message",
    [
        ("get-symbol-not-found", 'no symbol with id "nope"'),
        ("file-slice-bad-range", "invalid start/end line range"),
        ("file-slice-escape-root", "file path escapes repo root"),
        ("memory-add-invalid-kind", "invalid kind (want: rule, lesson, business, overview, reference)"),
    ],
)
def test_mcp_error_results_are_flagged_not_thrown(mcp_results: dict, op_id: str, message: str):
    result = mcp_results[op_id]["result"]
    assert result["isError"] is True
    assert result["content"] == [{"type": "text", "text": message}]
