"""A minimal re-implementation of the slice of spf13/cobra + spf13/pflag that
kb-core-ui's CLI surface actually uses.

The Go binary's help text, usage blocks, flag alignment and error wording are
frozen in the harness's cli-surface baselines, so this reproduces cobra's
rendering rather than approximating it with argparse. Every layout rule below
was derived from cobra's usage/help templates and pflag's FlagUsagesWrapped,
then checked against those recorded baselines.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from kb_core_ui.errors import KbError, UsageError

# cobra's minNamePadding: the "Available Commands" name column never shrinks
# below this even when every subcommand name is shorter.
_MIN_NAME_PADDING = 11


@dataclass
class Flag:
    name: str
    kind: str  # "string" | "int" | "bool"
    default: Any
    usage: str
    shorthand: str = ""

    @property
    def type_name(self) -> str:
        # pflag prints no type name for bools, so "--open" renders bare while
        # "--db string" carries one.
        return "" if self.kind == "bool" else self.kind

    def is_zero_default(self) -> bool:
        if self.kind == "bool":
            return self.default is False
        if self.kind == "int":
            return self.default == 0
        return self.default == ""

    def default_repr(self) -> str:
        if self.kind == "string":
            # pflag uses %q for strings, Go's quoting matches json.dumps here.
            import json

            return json.dumps(self.default)
        if self.kind == "bool":
            return "true" if self.default else "false"
        return str(self.default)


def _flag_usages(flags: Sequence[Flag]) -> str:
    """Reproduces pflag's FlagUsagesWrapped, including its deliberate
    off-by-one in the alignment column."""
    lines: list[str] = []
    maxlen = 0
    for f in sorted(flags, key=lambda x: x.name):
        if f.shorthand:
            line = f"  -{f.shorthand}, --{f.name}"
        else:
            line = f"      --{f.name}"
        if f.type_name:
            line += " " + f.type_name
        line += "\x00"
        if len(line) > maxlen:
            maxlen = len(line)
        usage = f.usage
        if not f.is_zero_default():
            usage += f" (default {f.default_repr()})"
        lines.append(line + usage)

    out: list[str] = []
    for line in lines:
        sidx = line.index("\x00")
        spacing = " " * (maxlen - sidx)
        # cobra's template pipes this through trimTrailingWhitespaces, so the
        # Fprintln-equivalent spacing is safe to emit here.
        out.append(f"{line[:sidx]} {spacing} {line[sidx + 1:]}")
    return "\n".join(out)


ArgsValidator = Callable[["Command", list[str]], None]


def no_args(cmd: "Command", args: list[str]) -> None:
    if args:
        raise UsageError(f'unknown command "{args[0]}" for "{cmd.command_path}"')


def exact_args(n: int) -> ArgsValidator:
    def validate(cmd: "Command", args: list[str]) -> None:
        if len(args) != n:
            raise UsageError(f"accepts {n} arg(s), received {len(args)}")

    return validate


def maximum_n_args(n: int) -> ArgsValidator:
    def validate(cmd: "Command", args: list[str]) -> None:
        if len(args) > n:
            raise UsageError(f"accepts at most {n} arg(s), received {len(args)}")

    return validate


def arbitrary_args(cmd: "Command", args: list[str]) -> None:
    return None


class Command:
    def __init__(
        self,
        use: str,
        short: str = "",
        long: str = "",
        flags: Sequence[Flag] = (),
        run: Callable[["Command", dict, list[str]], None] | None = None,
        args: ArgsValidator | None = None,
        disable_flag_parsing: bool = False,
    ):
        self.use = use
        self.short = short
        self.long = long
        self.run = run
        self.args_validator = args or arbitrary_args
        self.disable_flag_parsing = disable_flag_parsing
        self.parent: Command | None = None
        self.subcommands: list[Command] = []
        self.flags: list[Flag] = list(flags)
        self.flags.append(
            Flag("help", "bool", False, f"help for {self.name}", shorthand="h")
        )
        self.out = sys.stdout
        self.err = sys.stderr

    @property
    def name(self) -> str:
        return self.use.split(" ", 1)[0]

    def add(self, *cmds: "Command") -> "Command":
        for c in cmds:
            c.parent = self
            self.subcommands.append(c)
        return self

    @property
    def root(self) -> "Command":
        return self.parent.root if self.parent is not None else self

    def printf(self, text: str) -> None:
        """cobra's Command.Print* writes to OutOrStderr(), and SetOut is never
        called, so progress lines land on stderr rather than stdout."""
        self.root.err.write(text)

    @property
    def command_path(self) -> str:
        if self.parent is None:
            return self.name
        return f"{self.parent.command_path} {self.name}"

    @property
    def runnable(self) -> bool:
        return self.run is not None

    @property
    def has_subcommands(self) -> bool:
        return bool(self.subcommands)

    def use_line(self) -> str:
        line = self.use if self.parent is None else f"{self.parent.command_path} {self.use}"
        if self.flags and "[flags]" not in line:
            line += " [flags]"
        return line

    def _name_padding(self) -> int:
        # cobra reads the padding off the PARENT's widest child name, then
        # floors it at minNamePadding.
        widest = max((len(c.name) for c in self.subcommands), default=0)
        return max(widest, _MIN_NAME_PADDING)

    def usage_string(self) -> str:
        parts: list[str] = ["Usage:"]
        if self.runnable:
            parts.append(f"  {self.use_line()}")
        if self.has_subcommands:
            parts.append(f"  {self.command_path} [command]")

        if self.has_subcommands:
            pad = self._name_padding()
            parts.append("")
            parts.append("Available Commands:")
            for c in sorted(self.subcommands, key=lambda x: x.name):
                parts.append(f"  {c.name.ljust(pad)} {c.short}")

        if self.flags:
            parts.append("")
            parts.append("Flags:")
            parts.append(_flag_usages(self.flags))

        if self.has_subcommands:
            parts.append("")
            parts.append(
                f'Use "{self.command_path} [command] --help" for more information about a command.'
            )
        # cobra's usage template carries a trailing newline of its own.
        return "\n".join(parts) + "\n"

    def help_string(self) -> str:
        head = self.long or self.short
        body = self.usage_string() if (self.runnable or self.has_subcommands) else ""
        if head:
            return head.rstrip() + "\n\n" + body
        return body

    def find(self, args: list[str]) -> tuple["Command", list[str]]:
        """Walks into subcommands the way cobra's Find does, stopping at the
        first token that isn't a known child."""
        cmd = self
        rest = list(args)
        while rest and cmd.subcommands and not rest[0].startswith("-"):
            match = next((c for c in cmd.subcommands if c.name == rest[0]), None)
            if match is None:
                break
            cmd = match
            rest = rest[1:]
        return cmd, rest

    def parse_flags(self, argv: list[str]) -> tuple[dict, list[str]]:
        by_name = {f.name: f for f in self.flags}
        by_short = {f.shorthand: f for f in self.flags if f.shorthand}
        values: dict[str, Any] = {f.name: f.default for f in self.flags}
        positional: list[str] = []

        i = 0
        while i < len(argv):
            tok = argv[i]
            if tok == "--":
                positional.extend(argv[i + 1 :])
                break
            if tok.startswith("--"):
                body = tok[2:]
                inline: str | None = None
                if "=" in body:
                    body, inline = body.split("=", 1)
                flag = by_name.get(body)
                if flag is None:
                    raise UsageError(f"unknown flag: --{body}")
                i = self._consume(flag, values, argv, i, inline)
                continue
            if tok.startswith("-") and len(tok) > 1:
                body = tok[1:]
                inline = None
                if "=" in body:
                    body, inline = body.split("=", 1)
                flag = by_short.get(body)
                if flag is None:
                    raise UsageError(f"unknown shorthand flag: {body!r} in {tok}")
                i = self._consume(flag, values, argv, i, inline)
                continue
            positional.append(tok)
            i += 1

        return values, positional

    def _consume(
        self, flag: Flag, values: dict, argv: list[str], i: int, inline: str | None
    ) -> int:
        if flag.kind == "bool":
            values[flag.name] = True if inline is None else inline.lower() == "true"
            return i + 1
        if inline is not None:
            raw = inline
            nxt = i + 1
        else:
            if i + 1 >= len(argv):
                raise UsageError(f"flag needs an argument: --{flag.name}")
            raw = argv[i + 1]
            nxt = i + 2
        if flag.kind == "int":
            try:
                values[flag.name] = int(raw)
            except ValueError:
                raise UsageError(
                    f'invalid argument "{raw}" for "--{flag.name}" flag: '
                    f'strconv.ParseInt: parsing "{raw}": invalid syntax'
                ) from None
        else:
            values[flag.name] = raw
        return nxt


def execute(root: Command, argv: list[str]) -> int:
    """Mirrors cobra Execute() + kb-core-ui's main(): resolve the subcommand,
    parse flags, run, and on failure print cobra's error block followed by
    main.go's own "kb-core-ui: <err>" line."""
    err_out = root.err

    cmd, rest = root.find(argv)

    # An unresolved first token is cobra's Find error, which prints a short
    # hint instead of the full usage block.
    if rest and not rest[0].startswith("-") and cmd.has_subcommands:
        msg = f'unknown command "{rest[0]}" for "{cmd.command_path}"'
        print(f"Error: {msg}", file=err_out)
        print(f"Run '{root.command_path} --help' for usage.", file=err_out)
        print(f"{root.name}: {msg}", file=err_out)
        return 1

    try:
        if cmd.disable_flag_parsing:
            values, positional = {f.name: f.default for f in cmd.flags}, list(rest)
        else:
            values, positional = cmd.parse_flags(rest)

        if values.get("help"):
            root.out.write(cmd.help_string())
            return 0

        if not cmd.runnable:
            # A group command (root, memory, bot) invoked bare prints help and
            # exits 0, matching cobra's default when there is nothing to run.
            root.out.write(cmd.help_string())
            return 0

        cmd.args_validator(cmd, positional)
        cmd.run(cmd, values, positional)
        return 0
    except KbError as exc:
        msg = str(exc)
        print(f"Error: {msg}", file=err_out)
        print(cmd.usage_string(), file=err_out)
        print(f"{root.name}: {msg}", file=err_out)
        return 1
