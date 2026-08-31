"""Validation boundary for untrusted or stale KB Core graph JSON."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping, Sequence

from kb_core_ui.rag.contracts import GraphEnvelope, from_kb_core_graph


class NormalizationError(ValueError):
    pass


@dataclass(frozen=True)
class NormalizationLimits:
    max_nodes: int = 250_000
    max_relationships: int = 1_000_000
    max_id_chars: int = 2_048
    max_label_chars: int = 4_096
    max_text_chars: int = 131_072
    max_source_location_chars: int = 8_192
    max_record_json_bytes: int = 262_144


@dataclass(frozen=True)
class RejectedRecord:
    record_type: str
    index: int
    record_id: str
    reason: str

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "record_type": self.record_type,
            "index": self.index,
            "record_id": self.record_id,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class NormalizationResult:
    envelope: GraphEnvelope
    rejected: Sequence[RejectedRecord]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "envelope": self.envelope.to_json_dict(),
            "rejected": [item.to_json_dict() for item in self.rejected],
        }


def _records(graph: Mapping[str, Any], key: str, fallback: str | None = None) -> list[Any]:
    value = graph.get(key)
    if value is None and fallback is not None:
        value = graph.get(fallback, [])
    if value is None:
        value = []
    if not isinstance(value, list):
        raise NormalizationError(f"{key} must be a JSON array")
    return value


def _json_size(record: Mapping[str, Any]) -> int | None:
    try:
        return len(
            json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        )
    except (TypeError, ValueError):
        return None


def _too_long(record: Mapping[str, Any], fields: Mapping[str, int]) -> str:
    for field, limit in fields.items():
        value = record.get(field)
        if value is not None and len(str(value)) > limit:
            return f"{field} exceeds {limit} characters"
    return ""


def normalize_kb_core_graph(
    graph: Mapping[str, Any],
    *,
    workspace_id: str,
    source_id: str,
    source_uri: str = "",
    extractor_version: str = "kb-core-json.v1",
    limits: NormalizationLimits | None = None,
) -> NormalizationResult:
    """Validate records, reject bad entries, then emit one source envelope."""

    if not isinstance(graph, Mapping):
        raise NormalizationError("graph must be a JSON object")
    active_limits = limits or NormalizationLimits()
    raw_nodes = _records(graph, "nodes")
    raw_relationships = _records(graph, "links", "edges")
    if len(raw_nodes) > active_limits.max_nodes:
        raise NormalizationError(f"nodes exceeds limit {active_limits.max_nodes}")
    if len(raw_relationships) > active_limits.max_relationships:
        raise NormalizationError(
            f"relationships exceeds limit {active_limits.max_relationships}"
        )

    accepted_nodes: list[dict[str, Any]] = []
    accepted_node_ids: set[str] = set()
    rejected: list[RejectedRecord] = []
    node_fields = {
        "id": active_limits.max_id_chars,
        "label": active_limits.max_label_chars,
        "source_file": active_limits.max_source_location_chars,
        "source_location": active_limits.max_source_location_chars,
        "signature": active_limits.max_text_chars,
        "doc": active_limits.max_text_chars,
        "description": active_limits.max_text_chars,
    }
    for index, value in enumerate(raw_nodes):
        if not isinstance(value, Mapping):
            rejected.append(RejectedRecord("node", index, "", "record must be a JSON object"))
            continue
        record = dict(value)
        record_id = str(record.get("id", ""))
        reason = ""
        if not record_id:
            reason = "id is required"
        elif record_id in accepted_node_ids:
            reason = "duplicate node id"
        else:
            reason = _too_long(record, node_fields)
        size = _json_size(record)
        if not reason and size is None:
            reason = "record contains non-JSON value"
        elif not reason and size > active_limits.max_record_json_bytes:
            reason = f"record exceeds {active_limits.max_record_json_bytes} bytes"
        combined_text = "\n\n".join(
            str(record.get(key, "")).strip()
            for key in ("signature", "doc", "description")
            if str(record.get(key, "")).strip()
        )
        if not reason and len(combined_text) > active_limits.max_text_chars:
            reason = f"combined text exceeds {active_limits.max_text_chars} characters"
        if reason:
            rejected.append(RejectedRecord("node", index, record_id, reason))
            continue
        accepted_node_ids.add(record_id)
        accepted_nodes.append(record)

    accepted_relationships: list[dict[str, Any]] = []
    relationship_keys: set[str] = set()
    edge_fields = {
        "source": active_limits.max_id_chars,
        "target": active_limits.max_id_chars,
        "relation": active_limits.max_label_chars,
        "kind": active_limits.max_label_chars,
        "source_location": active_limits.max_source_location_chars,
    }
    for index, value in enumerate(raw_relationships):
        if not isinstance(value, Mapping):
            rejected.append(
                RejectedRecord("relationship", index, "", "record must be a JSON object")
            )
            continue
        record = dict(value)
        raw_source = str(record.get("source", ""))
        raw_target = str(record.get("target", ""))
        record_id = f"{raw_source}->{raw_target}"
        reason = _too_long(record, edge_fields)
        if not reason and (not raw_source or not raw_target):
            reason = "source and target are required"
        elif not reason and (
            raw_source not in accepted_node_ids or raw_target not in accepted_node_ids
        ):
            reason = "dangling endpoint"
        size = _json_size(record)
        if not reason and size is None:
            reason = "record contains non-JSON value"
        elif not reason and size > active_limits.max_record_json_bytes:
            reason = f"record exceeds {active_limits.max_record_json_bytes} bytes"
        edge_key = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":")) if size is not None else ""
        if not reason and edge_key in relationship_keys:
            reason = "duplicate relationship"
        if reason:
            rejected.append(RejectedRecord("relationship", index, record_id, reason))
            continue
        relationship_keys.add(edge_key)
        accepted_relationships.append(record)

    envelope = from_kb_core_graph(
        {"nodes": accepted_nodes, "links": accepted_relationships},
        workspace_id=workspace_id,
        source_id=source_id,
        source_uri=source_uri,
        extractor_version=extractor_version,
    )
    return NormalizationResult(envelope=envelope, rejected=tuple(rejected))
