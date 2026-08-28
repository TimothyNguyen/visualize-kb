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
