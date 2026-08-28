from __future__ import annotations


class KbError(Exception):
    """Base for every error whose message is part of the CLI/REST contract.

    str(exc) is rendered verbatim, so message text is as load-bearing as any
    status code — the T1 baselines compare it byte for byte.
    """


class UsageError(KbError):
    """A bad invocation: unknown flag, wrong arg count, missing required flag."""


class RepoPathError(KbError):
    """The positional repo path is missing or is not a directory."""


class StoreError(KbError):
    pass


class MemoryError_(KbError):
    pass


class ParserError(KbError):
    pass


class IndexError_(KbError):
    pass


def os_error_text(op: str, path: str, exc: OSError) -> str:
    """Renders a failed file operation the way Go's *os.PathError does:
    "<op> <path>: <err>".

    The wrapped message is the platform's, and the platforms disagree with
    Python. On Windows, Go reports the Win32 text ("The system cannot find
    the file specified."), but Python's open() reports the POSIX errno text
    and leaves winerror unset; os.stat does surface winerror, so the Windows
    message is recovered from there. On POSIX, Go's errno table is the
    lowercase form of C's, which is what Python returns.
    """
    import ctypes
    import os

    winerror = getattr(exc, "winerror", None)
    if winerror is None and os.name == "nt":
        try:
            os.stat(path)
        except OSError as stat_exc:
            winerror = getattr(stat_exc, "winerror", None)
    if winerror:
        return f"{op} {path}: {ctypes.FormatError(winerror)}"
    message = exc.strerror or str(exc)
    return f"{op} {path}: {message[:1].lower()}{message[1:]}"
