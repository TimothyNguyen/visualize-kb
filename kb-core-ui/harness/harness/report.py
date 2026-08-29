from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from harness.canonical import canonical_dumps
from harness.diff import DiffEntry, DiffResult


@dataclass
class ParityResult:
    fixture: str
    operation_id: str
    oracle_engine: str
    candidate_engine: str
    diff: DiffResult | None = None
    error: str | None = None


@dataclass
class RunReport:
    mode: str
    started_at: str
    finished_at: str
    engine_pair: tuple[str, str]
    results: list[ParityResult] = field(default_factory=list)
    passed: int = 0
    failed: int = 0
    errored: int = 0


def _entry_to_dict(e: DiffEntry) -> dict:
    return {"path": e.path, "kind": e.kind, "oracle": e.oracle, "candidate": e.candidate}


def _entry_from_dict(d: dict) -> DiffEntry:
    return DiffEntry(path=d["path"], kind=d["kind"], oracle=d["oracle"], candidate=d["candidate"])


def _diff_to_dict(r: DiffResult) -> dict:
    return {
        "case_id": r.case_id,
        "equal": r.equal,
        "entries": [_entry_to_dict(e) for e in r.entries],
        "ignored": [_entry_to_dict(e) for e in r.ignored],
    }


def _diff_from_dict(d: dict) -> DiffResult:
    return DiffResult(
        case_id=d["case_id"],
        equal=d["equal"],
        entries=[_entry_from_dict(e) for e in d["entries"]],
        ignored=[_entry_from_dict(e) for e in d["ignored"]],
    )


def _result_to_dict(p: ParityResult) -> dict:
    return {
        "fixture": p.fixture,
        "operation_id": p.operation_id,
        "oracle_engine": p.oracle_engine,
        "candidate_engine": p.candidate_engine,
        "diff": _diff_to_dict(p.diff) if p.diff is not None else None,
        "error": p.error,
    }


def _result_from_dict(d: dict) -> ParityResult:
    return ParityResult(
        fixture=d["fixture"],
        operation_id=d["operation_id"],
        oracle_engine=d["oracle_engine"],
        candidate_engine=d["candidate_engine"],
        diff=_diff_from_dict(d["diff"]) if d.get("diff") is not None else None,
        error=d.get("error"),
    )


def report_to_dict(report: RunReport) -> dict:
    return {
        "mode": report.mode,
        "started_at": report.started_at,
        "finished_at": report.finished_at,
        "engine_pair": list(report.engine_pair),
        "results": [_result_to_dict(r) for r in report.results],
        "passed": report.passed,
        "failed": report.failed,
        "errored": report.errored,
    }


def report_from_dict(d: dict) -> RunReport:
    return RunReport(
        mode=d["mode"],
        started_at=d["started_at"],
        finished_at=d["finished_at"],
        engine_pair=tuple(d["engine_pair"]),
        results=[_result_from_dict(r) for r in d["results"]],
        passed=d["passed"],
        failed=d["failed"],
        errored=d["errored"],
    )


def write_report(path: Path, report: RunReport) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_dumps(report_to_dict(report)), encoding="utf-8")


def read_report(path: Path) -> RunReport:
    return report_from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def render_text(report: RunReport, *, max_diff_entries: int = 20) -> str:
    lines = [
        f"== {report.mode} report: {report.engine_pair[0]} vs {report.engine_pair[1]} ==",
        f"passed={report.passed} failed={report.failed} errored={report.errored}",
        "",
    ]
    for r in report.results:
        if r.error:
            lines.append(f"[ERROR] {r.fixture}/{r.operation_id}: {r.error}")
        elif r.diff is not None and not r.diff.equal:
            lines.append(f"[FAIL]  {r.fixture}/{r.operation_id} ({len(r.diff.entries)} diff(s))")
            for entry in r.diff.entries[:max_diff_entries]:
                lines.append(
                    f"    {entry.path}: {entry.kind} oracle={entry.oracle!r} candidate={entry.candidate!r}"
                )
        else:
            lines.append(f"[PASS]  {r.fixture}/{r.operation_id}")
    return "\n".join(lines) + "\n"


def render_json(report: RunReport) -> str:
    return canonical_dumps(report_to_dict(report))
