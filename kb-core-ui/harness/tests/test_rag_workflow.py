from __future__ import annotations

import json
from pathlib import Path

from harness.rag_workflow import REQUIRED_STAGES, execute_rag_workflow


FIXTURE = Path(__file__).parent / "fixtures" / "rag-workflow" / "sources.json"


def test_dynamic_rag_workflow_composes_t1_through_t4(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"

    report = execute_rag_workflow(
        backend="fake",
        fixture_path=FIXTURE,
        work_dir=tmp_path / "work",
        report_path=report_path,
    )

    assert report["status"] == "passed"
    assert [stage["name"] for stage in report["stages"]] == list(REQUIRED_STAGES)
    assert {stage["status"] for stage in report["stages"]} == {"passed"}
    assert json.loads(report_path.read_text(encoding="utf-8")) == report

    delete_stage = next(
        stage for stage in report["stages"] if stage["name"] == "source_delete_isolation"
    )
    assert delete_stage["details"] == {
        "deleted_source": "repo",
        "remaining_nodes": 3,
        "source_ids": ["docs"],
    }
