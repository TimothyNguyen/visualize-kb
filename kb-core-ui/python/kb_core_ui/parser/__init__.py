"""Turns source files into FileGraph values using tree-sitter grammars."""

from __future__ import annotations

import os
from typing import Callable

from kb_core_ui.errors import ParserError
from kb_core_ui.models import FileGraph
from kb_core_ui.parser.golang import parse_go
from kb_core_ui.parser.jslang import parse_javascript, parse_tsx, parse_typescript
from kb_core_ui.parser.pylang import parse_python

ParseFunc = Callable[[str, bytes], FileGraph]

_BY_EXT: dict[str, ParseFunc] = {
    ".go": parse_go,
    ".ts": parse_typescript,
    ".tsx": parse_tsx,
    ".js": parse_javascript,
    ".jsx": parse_javascript,
    ".mjs": parse_javascript,
    ".py": parse_python,
}

_LANGUAGE_BY_EXT = {
    ".go": "go",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".mjs": "javascript",
    ".jsx": "javascript",
    ".py": "python",
}


def supported_extensions() -> list[str]:
    return list(_BY_EXT)


def language_for(path: str) -> tuple[str, bool]:
    lang = _LANGUAGE_BY_EXT.get(os.path.splitext(path)[1])
    return (lang, True) if lang else ("", False)


def parse_file(file_path: str, src: bytes) -> FileGraph:
    fn = _BY_EXT.get(os.path.splitext(file_path)[1])
    if fn is None:
        raise ParserError(f"parser: no parser registered for {file_path}")
    return fn(file_path, src)
