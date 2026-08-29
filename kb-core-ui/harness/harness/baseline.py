from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from harness.canonical import canonical_dumps


@dataclass(frozen=True)
class RecordedCase:
    fixture: str
    operation_id: str
    engine: str
    captured_at: str
    harness_version: str
    normalizers: list[str]
    ignore_fields: list[str]
    comparable: Any


def baseline_path(fixtures_root: Path, fixture: str, operation_id: str) -> Path:
    return Path(fixtures_root) / fixture / "baseline" / f"{operation_id}.json"


def write_baseline(path: Path, case: RecordedCase) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_dumps(asdict(case)), encoding="utf-8")


def read_baseline(path: Path) -> RecordedCase:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return RecordedCase(**raw)
