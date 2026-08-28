from __future__ import annotations

import sys

from kb_core_ui.cli.command import execute
from kb_core_ui.cli.root import build_root


def main() -> int:
    # Go writes UTF-8 with bare \n on every platform. Python's default text
    # streams would encode with the Windows locale codepage and translate \n
    # to \r\n, so the CLI's bytes have to be pinned here.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", newline="")
    root = build_root()
    root.out = sys.stdout
    root.err = sys.stderr
    return execute(root, sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
