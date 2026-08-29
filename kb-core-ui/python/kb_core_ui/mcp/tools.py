"""Tool declarations and result envelopes.

The shapes here are not free choices: `tools/list` is a recorded baseline
(SPEC.md I.mcp), and mark3labs/mcp-go generates those schemas from its
mcp.WithString/WithNumber builders. Tool, Param and the result helpers below
reproduce what that generator emits, so a new tool is declared the same way
on both sides instead of being hand-written JSON that drifts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kb_core_ui import jsonx

# mcp-go stamps every tool with the zero-value ToolAnnotation block unless the
# server opts out, and kb-core-ui never does. The values read oddly for
# read-only tools (destructiveHint true, readOnlyHint false), but they are
# what the Go server serves, so they are contract.
DEFAULT_ANNOTATIONS: dict[str, bool] = {
    "destructiveHint": True,
    "idempotentHint": False,
    "openWorldHint": True,
    "readOnlyHint": False,
}


@dataclass(frozen=True)
class Param:
    name: str
    type: str
    description: str
    required: bool = False


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    params: tuple[Param, ...] = ()
    handler: Any = None

    def to_json_dict(self) -> dict:
        properties = {
            p.name: {"description": p.description, "type": p.type} for p in self.params
        }
        return {
            "annotations": dict(DEFAULT_ANNOTATIONS),
            "description": self.description,
            "inputSchema": {
                "properties": properties,
                # Declaration order, not sorted: mcp-go appends each required
                # param as it is declared.
                "required": [p.name for p in self.params if p.required],
                "type": "object",
            },
            "name": self.name,
        }


@dataclass
class ToolResult:
    text: str
    is_error: bool = False

    def to_json_dict(self) -> dict:
        out: dict = {"content": [{"type": "text", "text": self.text}]}
        # mcp-go tags IsError omitempty, so a success result carries no
        # isError key at all.
        if self.is_error:
            out["isError"] = True
        return out


def text_result(text: str) -> ToolResult:
    return ToolResult(text=text)


def json_result(value: Any) -> ToolResult:
    """mcp.NewToolResultText(string(json.Marshal(v))) — the payload is JSON
    *inside* a text block, not structured content."""
    return ToolResult(text=jsonx.dumps(value))


def error_result(text: str) -> ToolResult:
    return ToolResult(text=text, is_error=True)


def error_from_exc(prefix: str, exc: BaseException) -> ToolResult:
    """mcp.NewToolResultErrorFromErr(prefix, err) renders "<prefix>: <err>"."""
    return ToolResult(text=f"{prefix}: {exc}", is_error=True)


def parse_string(arguments: dict, name: str, default: str = "") -> str:
    value = arguments.get(name)
    return value if isinstance(value, str) else default


def parse_int(arguments: dict, name: str, default: int) -> int:
    """mcp.ParseInt accepts any JSON number and truncates; a missing or
    non-numeric argument falls back to the default."""
    value = arguments.get(name)
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return default
    return default


@dataclass
class Registry:
    tools: list[Tool] = field(default_factory=list)

    def add(self, tool: Tool) -> None:
        self.tools.append(tool)

    def listing(self) -> dict:
        # mcp-go serves tools/list sorted by name, not in registration order.
        return {"tools": [t.to_json_dict() for t in sorted(self.tools, key=lambda t: t.name)]}

    def lookup(self, name: str) -> Tool | None:
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None
