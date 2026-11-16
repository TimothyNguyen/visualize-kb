from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from harness.engines import EngineError, resolve_go_binary

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def go_bin() -> str:
    try:
        return resolve_go_binary(None)
    except EngineError:
        pytest.skip(
            "no kb-core-ui binary found — build with "
            "`go build -o kb-core-ui.exe ./cmd/kb-core-ui` from kb-core-ui/legacy/go/"
        )


@pytest.fixture()
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture()
def tmp_fixtures_dir(tmp_path: Path) -> Path:
    """A writable copy of tests/fixtures, so tests that mutate a fixture's
    repo or record/corrupt baselines don't touch the committed originals."""
    dest = tmp_path / "fixtures"
    shutil.copytree(FIXTURES_DIR, dest)
    return dest


def make_args(mode: str, **overrides) -> "argparse.Namespace":
    import argparse

    defaults = {
        "fixtures_dir": str(FIXTURES_DIR),
        "work_dir": ".harness-work",
        "go_bin": None,
        "python_bin": None,
        "keep_work_dir": False,
        "verbose": False,
    }
    if mode == "record":
        defaults["engine"] = "go"
    elif mode == "parity":
        defaults.update({"oracle": "go", "candidate": "go", "out_dir": None})
    elif mode == "report":
        defaults.update({"in_path": None, "format": "text"})
    defaults.update(overrides)
    return argparse.Namespace(**defaults)
