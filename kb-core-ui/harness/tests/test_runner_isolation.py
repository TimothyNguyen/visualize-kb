from __future__ import annotations

from pathlib import Path

from harness.engines import EngineConfig, ResolvedEngine
from harness.manifest import discover_fixtures
from harness.runner import ProcessRunner

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _dummy_engine() -> ResolvedEngine:
    config = EngineConfig(name="dummy", resolve_bin=lambda explicit: "dummy-bin", cli_templates={})
    return ResolvedEngine(config=config, bin_path="dummy-bin")


def test_prepare_run_creates_isolated_roots(tmp_path: Path):
    fixture = discover_fixtures(FIXTURES_DIR)[0]
    runner = ProcessRunner(_dummy_engine(), tmp_path)

    ctx1 = runner.prepare_run(fixture, "run1")
    ctx2 = runner.prepare_run(fixture, "run2")

    assert ctx1.root != ctx2.root
    assert ctx1.fixture_root != ctx2.fixture_root
    assert ctx1.db_path != ctx2.db_path
    assert ctx1.fixture_root.is_dir()
    assert ctx2.fixture_root.is_dir()
    assert (ctx1.fixture_root / "hello.go").is_file()
    assert (ctx2.fixture_root / "hello.go").is_file()


def test_marker_written_in_one_run_does_not_leak_into_another(tmp_path: Path):
    fixture = discover_fixtures(FIXTURES_DIR)[0]
    runner = ProcessRunner(_dummy_engine(), tmp_path)

    ctx1 = runner.prepare_run(fixture, "run1")
    ctx2 = runner.prepare_run(fixture, "run2")

    (ctx1.fixture_root / ".kb-core-ui").mkdir()
    (ctx1.fixture_root / ".kb-core-ui" / "memory.db").write_text("x", encoding="utf-8")

    assert not (ctx2.fixture_root / ".kb-core-ui").exists()


def test_cleanup_removes_run_root(tmp_path: Path):
    fixture = discover_fixtures(FIXTURES_DIR)[0]
    runner = ProcessRunner(_dummy_engine(), tmp_path)

    ctx = runner.prepare_run(fixture, "run1")
    assert ctx.root.exists()
    runner.cleanup(ctx)
    assert not ctx.root.exists()


def test_concurrent_prepare_run_and_writes_do_not_interfere(tmp_path: Path):
    from concurrent.futures import ThreadPoolExecutor

    fixture = discover_fixtures(FIXTURES_DIR)[0]
    runner = ProcessRunner(_dummy_engine(), tmp_path)

    def _do(label: str) -> Path:
        ctx = runner.prepare_run(fixture, label)
        (ctx.fixture_root / "marker.txt").write_text(label, encoding="utf-8")
        return ctx.fixture_root

    with ThreadPoolExecutor(max_workers=2) as pool:
        roots = list(pool.map(_do, ["a", "b"]))

    assert roots[0] != roots[1]
    assert (roots[0] / "marker.txt").read_text(encoding="utf-8") == "a"
    assert (roots[1] / "marker.txt").read_text(encoding="utf-8") == "b"
