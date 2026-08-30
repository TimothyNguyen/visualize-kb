from __future__ import annotations

import pytest

from harness.engines import (
    ENGINES,
    EngineConfig,
    bin_override_for,
    get_engine,
    render_argv,
    resolve_go_binary,
)
from harness.errors import EngineError


def test_render_argv_substitutes_placeholders():
    argv = render_argv(["{bin}", "parse", "{repo}", "--db", "{db}"], {"bin": "kb", "repo": "R", "db": "D"})
    assert argv == ["kb", "parse", "R", "--db", "D"]


def test_render_argv_missing_placeholder_raises():
    with pytest.raises(EngineError):
        render_argv(["{bin}", "{missing}"], {"bin": "kb"})


def test_get_engine_unknown_name_raises():
    with pytest.raises(EngineError):
        get_engine("no-such-engine")


def test_get_engine_go_with_bin_override():
    resolved = get_engine("go", bin_override="explicit/path/to/kb-core-ui")
    assert resolved.config.name == "go"
    assert resolved.bin_path == "explicit/path/to/kb-core-ui"


def test_resolve_go_binary_explicit_short_circuits(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("KB_CORE_UI_BIN", "should-not-be-used")
    assert resolve_go_binary("explicit-bin") == "explicit-bin"


def test_resolve_go_binary_env_var(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("KB_CORE_UI_BIN", "from-env")
    assert resolve_go_binary(None) == "from-env"


def test_resolve_go_binary_raises_helpful_error_when_missing(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.delenv("KB_CORE_UI_BIN", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)
    fake_engines_file = tmp_path / "somewhere" / "harness" / "harness" / "engines.py"
    fake_engines_file.parent.mkdir(parents=True)
    monkeypatch.setattr("harness.engines.__file__", str(fake_engines_file))
    with pytest.raises(EngineError, match="from kb-core-ui/legacy/go/"):
        resolve_go_binary(None)


@pytest.mark.parametrize("stale_root_build", [False, True])
def test_go_oracle_never_uses_python_console_script_on_path(monkeypatch, tmp_path, stale_root_build):
    monkeypatch.delenv("KB_CORE_UI_BIN", raising=False)
    root = tmp_path / "kb-core-ui"
    root.mkdir()
    monkeypatch.setattr("harness.engines.__file__", str(root / "harness/harness/engines.py"))
    # Both a stale root-level Go build and a Python entry point must be ignored.
    if stale_root_build:
        (root / "kb-core-ui.exe").touch()
        (root / "kb-core-ui").touch()
    monkeypatch.setattr("shutil.which", lambda name: "/venv/bin/kb-core-ui")
    with pytest.raises(EngineError, match="legacy/go"):
        resolve_go_binary()


@pytest.mark.parametrize("name", ["kb-core-ui.exe", "kb-core-ui"])
def test_go_oracle_resolves_legacy_build(monkeypatch, tmp_path, name):
    monkeypatch.delenv("KB_CORE_UI_BIN", raising=False)
    monkeypatch.setattr("harness.engines.__file__", str(tmp_path / "harness/harness/engines.py"))
    binary = tmp_path / "legacy/go" / name
    binary.parent.mkdir(parents=True)
    binary.touch()
    assert resolve_go_binary() == str(binary)


def test_bin_override_for_reads_named_argparse_attr():
    class Args:
        go_bin = "g"
        python_bin = "p"

    assert bin_override_for(Args(), "go") == "g"
    assert bin_override_for(Args(), "python") == "p"
    assert bin_override_for(Args(), "rust") is None


def test_engines_registry_is_pure_config_addition():
    original = dict(ENGINES)
    try:
        ENGINES["fake-test-engine"] = EngineConfig(
            name="fake-test-engine",
            resolve_bin=lambda explicit: explicit or "fake-bin",
            cli_templates={"noop": ["{bin}"]},
        )
        resolved = get_engine("fake-test-engine")
        assert resolved.bin_path == "fake-bin"
    finally:
        ENGINES.clear()
        ENGINES.update(original)
