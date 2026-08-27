"""Per-language extractors, incrementally migrated out of kb-core/extract.py.

Dispatch still flows through kb_core.extract (the facade re-exports every
moved name), so importing from kb_core.extract keeps working unchanged.
LANGUAGE_EXTRACTORS is the registry seed; wiring dispatch through it is a
later, separate step. See MIGRATION.md for how to port another language.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from kb_core.extractors.apex import extract_apex
from kb_core.extractors.bash import extract_bash
from kb_core.extractors.blade import extract_blade
from kb_core.extractors.commonlisp import extract_commonlisp
from kb_core.extractors.dart import extract_dart
from kb_core.extractors.dm import extract_dm, extract_dmf, extract_dmi, extract_dmm
from kb_core.extractors.elixir import extract_elixir
from kb_core.extractors.fortran import extract_fortran
from kb_core.extractors.go import extract_go
from kb_core.extractors.json_config import extract_json
from kb_core.extractors.julia import extract_julia
from kb_core.extractors.markdown import extract_markdown
from kb_core.extractors.objc import extract_objc
from kb_core.extractors.pascal import extract_pascal
from kb_core.extractors.pascal_forms import extract_delphi_form, extract_lazarus_form
from kb_core.extractors.powershell import extract_powershell, extract_powershell_manifest
from kb_core.extractors.razor import extract_razor
from kb_core.extractors.rust import extract_rust
from kb_core.extractors.sln import extract_sln
from kb_core.extractors.sql import extract_sql
from kb_core.extractors.terraform import extract_terraform
from kb_core.extractors.verilog import extract_verilog
from kb_core.extractors.zig import extract_zig

LANGUAGE_EXTRACTORS: dict[str, Callable[[Path], dict]] = {
    "apex": extract_apex,
    "bash": extract_bash,
    "blade": extract_blade,
    "commonlisp": extract_commonlisp,
    "dart": extract_dart,
    "delphi_form": extract_delphi_form,
    "dm": extract_dm,
    "dmf": extract_dmf,
    "dmi": extract_dmi,
    "dmm": extract_dmm,
    "elixir": extract_elixir,
    "fortran": extract_fortran,
    "go": extract_go,
    "json": extract_json,
    "julia": extract_julia,
    "lazarus_form": extract_lazarus_form,
    "markdown": extract_markdown,
    "objc": extract_objc,
    "pascal": extract_pascal,
    "powershell": extract_powershell,
    "powershell_manifest": extract_powershell_manifest,
    "razor": extract_razor,
    "rust": extract_rust,
    "sln": extract_sln,
    "sql": extract_sql,
    "terraform": extract_terraform,
    "verilog": extract_verilog,
    "zig": extract_zig,
}
