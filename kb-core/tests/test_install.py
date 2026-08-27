"""Tests for kb-core install --platform routing."""
import os
from pathlib import Path
import sys
from unittest.mock import patch
import pytest


def _install(tmp_path, platform):
    from kb_core.__main__ import install

    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        with patch("kb_core.__main__.Path.home", return_value=tmp_path):
            install(platform=platform)
    finally:
        os.chdir(old_cwd)


def test_install_default_claude(tmp_path):
    _install(tmp_path, "claude")
    assert (tmp_path / ".claude" / "skills" / "kb-core" / "SKILL.md").exists()


def test_install_claude_md_honors_claude_config_dir(tmp_path, monkeypatch):
    """#2694: with CLAUDE_CONFIG_DIR set, the always-on registration lands in
    $CLAUDE_CONFIG_DIR/CLAUDE.md — not the default ~/.claude/CLAUDE.md, which the
    old code mutated regardless of the relocated profile."""
    from kb_core.__main__ import install

    home = tmp_path / "home"
    home.mkdir()
    config = tmp_path / "cfg"
    config.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        with patch("kb_core.__main__.Path.home", return_value=home):
            install(platform="claude")
    finally:
        os.chdir(old)

    cfg_md = config / "CLAUDE.md"
    assert cfg_md.exists(), "registration did not land in $CLAUDE_CONFIG_DIR"
    text = cfg_md.read_text()
    assert "# kb-core" in text
    assert str(config) in text, "skill reference does not point into the config dir"
    assert not (home / ".claude" / "CLAUDE.md").exists(), "default profile was mutated"


def test_install_claude_md_defaults_to_home_when_config_dir_unset(tmp_path, monkeypatch):
    """Env unset: behavior is unchanged — the block lands in ~/.claude/CLAUDE.md
    with the tilde skill reference."""
    from kb_core.__main__ import install

    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        with patch("kb_core.__main__.Path.home", return_value=tmp_path):
            install(platform="claude")
    finally:
        os.chdir(old)

    md = tmp_path / ".claude" / "CLAUDE.md"
    assert md.exists()
    assert "~/.claude/skills/kb-core/SKILL.md" in md.read_text()


def test_install_codex(tmp_path):
    _install(tmp_path, "codex")
    assert (tmp_path / ".codex" / "skills" / "kb-core" / "SKILL.md").exists()


def test_install_help_does_not_install_default(tmp_path, monkeypatch, capsys):
    from kb_core.__main__ import main
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["kb-core", "install", "codex", "--help"])
    with patch("kb_core.__main__.Path.home", return_value=tmp_path):
        main()
    out = capsys.readouterr().out
    assert "Usage: kb-core install" in out
    assert "codex" in out
    assert not (tmp_path / ".claude").exists()
    assert not (tmp_path / ".codex").exists()


def test_install_project_claude_writes_project_scope(tmp_path, monkeypatch, capsys):
    from kb_core.__main__ import main
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    monkeypatch.setattr(sys, "argv", ["kb-core", "install", "--project"])
    with patch("kb_core.__main__.Path.home", return_value=home):
        main()
    assert (project / ".claude" / "skills" / "kb-core" / "SKILL.md").exists()
    assert (project / ".claude" / "CLAUDE.md").exists()
    assert not (home / ".claude" / "skills" / "kb-core" / "SKILL.md").exists()
    assert ".claude/skills/kb-core/SKILL.md" in (project / ".claude" / "CLAUDE.md").read_text()
    assert "~/.claude/skills/kb-core/SKILL.md" not in (project / ".claude" / "CLAUDE.md").read_text()
    assert "git add .claude/" in capsys.readouterr().out


def test_install_project_codex_writes_skill_and_agents(tmp_path, monkeypatch):
    from kb_core.__main__ import main
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    monkeypatch.setattr(sys, "argv", ["kb-core", "install", "--project", "--platform", "codex"])
    with patch("kb_core.__main__.Path.home", return_value=home):
        main()
    assert (project / ".codex" / "skills" / "kb-core" / "SKILL.md").exists()
    assert (project / "AGENTS.md").exists()
    assert (project / ".codex" / "hooks.json").exists()
    assert not (home / ".codex" / "skills" / "kb-core" / "SKILL.md").exists()


def test_claude_subcommand_project_install_and_uninstall_are_project_scoped(tmp_path, monkeypatch):
    from kb_core.__main__ import main
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    user_skill = home / ".claude" / "skills" / "kb-core" / "SKILL.md"
    user_skill.parent.mkdir(parents=True)
    user_skill.write_text("user skill")
    monkeypatch.chdir(project)
    with patch("kb_core.__main__.Path.home", return_value=home):
        monkeypatch.setattr(sys, "argv", ["kb-core", "claude", "install", "--project"])
        main()
        assert (project / ".claude" / "skills" / "kb-core" / "SKILL.md").exists()
        assert (project / ".claude" / "CLAUDE.md").exists()
        assert (project / "CLAUDE.md").exists()
        assert user_skill.exists()

        monkeypatch.setattr(sys, "argv", ["kb-core", "claude", "uninstall", "--project"])
        main()

    assert user_skill.exists()
    assert not (project / ".claude" / "skills" / "kb-core" / "SKILL.md").exists()
    assert not (project / ".claude" / "CLAUDE.md").exists()
    assert not (project / "CLAUDE.md").exists()


def test_codex_subcommand_project_install_and_uninstall_are_project_scoped(tmp_path, monkeypatch):
    from kb_core.__main__ import main
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    user_skill = home / ".codex" / "skills" / "kb-core" / "SKILL.md"
    user_skill.parent.mkdir(parents=True)
    user_skill.write_text("user skill")
    monkeypatch.chdir(project)
    with patch("kb_core.__main__.Path.home", return_value=home):
        monkeypatch.setattr(sys, "argv", ["kb-core", "codex", "install", "--project"])
        main()
        assert (project / ".codex" / "skills" / "kb-core" / "SKILL.md").exists()
        assert (project / "AGENTS.md").exists()
        assert (project / ".codex" / "hooks.json").exists()
        assert user_skill.exists()

        monkeypatch.setattr(sys, "argv", ["kb-core", "codex", "uninstall", "--project"])
        main()

    assert user_skill.exists()
    assert not (project / ".codex" / "skills" / "kb-core" / "SKILL.md").exists()
    assert not (project / "AGENTS.md").exists()
    hooks_path = project / ".codex" / "hooks.json"
    assert hooks_path.exists()
    assert "kb-core" not in hooks_path.read_text()


def test_install_windows(tmp_path):
    _install(tmp_path, "windows")
    assert (tmp_path / ".claude" / "skills" / "kb-core" / "SKILL.md").exists()


def test_install_unknown_platform_exits(tmp_path):
    with pytest.raises(SystemExit):
        _install(tmp_path, "unknown")


def test_codex_skill_contains_spawn_agent():
    """Codex skill file must reference spawn_agent."""
    import kb_core

    skill = (Path(kb_core.__file__).parent / "skill-codex.md").read_text()
    assert "spawn_agent" in skill


def test_codex_skill_uses_kb_core_with_existing_graph():
    """Codex skill must keep graph-first orientation in the lean-core split.

    The progressive-disclosure split drops codex's old monolith-only "dirty
    graph output" blurb; the graph-first intent now lives in the shared core's
    fast-path block, which jumps straight to the query flow when a graph exists.
    """
    import kb_core
    skill = (Path(kb_core.__file__).parent / "skill-codex.md").read_text()
    assert "existing graph" in skill
    assert "$kb-core query" in skill
    assert "/kb-core" not in skill
    assert "kb-core query" in skill
    assert "kb-core explain" in skill
    assert "kb-core path" in skill


def test_codex_agents_install_mentions_dirty_graph_output(tmp_path):
    from kb_core.__main__ import _codex_agents_md_install

    _codex_agents_md_install(tmp_path)
    content = (tmp_path / "AGENTS.md").read_text()
    assert "Dirty kb-core-out/ files are expected" in content
    assert "not a reason to skip kb-core" in content


def test_all_skill_files_exist_in_package():
    """All installable platform skill files must be present in the installed package."""
    import kb_core

    pkg = Path(kb_core.__file__).parent
    for name in (
        "skill.md",
        "skill-codex.md",
        "skill-copilot.md",
        "skill-windows.md",
        "skill-vscode.md",
    ):
        assert (pkg / name).exists(), f"Missing: {name}"


def test_claude_install_registers_claude_md(tmp_path):
    """Claude platform install writes CLAUDE.md; others do not."""
    _install(tmp_path, "claude")
    assert (tmp_path / ".claude" / "CLAUDE.md").exists()


def test_codex_install_does_not_write_claude_md(tmp_path):
    _install(tmp_path, "codex")
    assert not (tmp_path / ".claude" / "CLAUDE.md").exists()


def test_claude_hook_is_shell_agnostic(tmp_path):
    # #522: the installed PreToolUse hooks must be plain exe invocations, not
    # POSIX bash (which fails on Windows cmd.exe/PowerShell).
    import json as _json
    from kb_core.__main__ import _install_claude_hook
    _install_claude_hook(tmp_path)
    hooks = _json.loads((tmp_path / ".claude" / "settings.json").read_text())["hooks"]["PreToolUse"]
    matchers = {h["matcher"] for h in hooks}
    assert {"Bash|Grep", "Read|Glob"} <= matchers  # Grep in the search matcher: #1986
    for h in hooks:
        cmd = h["hooks"][0]["command"]
        for token in ("$(", "case ", "[ -f", "&&", "||", ";;", "echo '"):
            assert token not in cmd, f"shell syntax {token!r} in {cmd!r}"
        assert "kb-core" in cmd and "hook-guard" in cmd


def test_claude_hook_install_idempotent_and_replaces_old_bash_hook(tmp_path):
    import json as _json
    from kb_core.__main__ import _install_claude_hook
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    # Pre-seed a legacy bash-style kb_core hook (the thing #522 shipped before).
    settings_path.write_text(_json.dumps({"hooks": {"PreToolUse": [
        {"matcher": "Bash", "hooks": [{"type": "command",
         "command": "[ -f kb-core-out/graph.json ] && echo '{...}' || true"}]},
    ]}}), encoding="utf-8")
    _install_claude_hook(tmp_path)
    _install_claude_hook(tmp_path)  # second install must not duplicate
    hooks = _json.loads(settings_path.read_text())["hooks"]["PreToolUse"]
    kb_core_hooks = [h for h in hooks if "kb-core" in str(h)]
    assert len(kb_core_hooks) == 2, "exactly the Bash + Read|Glob guards, no dupes"
    # the legacy bash payload must be gone
    assert not any("[ -f kb-core-out" in h["hooks"][0]["command"] for h in kb_core_hooks)


def test_uninstall_project_removes_project_skill_only(tmp_path, monkeypatch):
    from kb_core.__main__ import main
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    user_skill = home / ".codex" / "skills" / "kb-core" / "SKILL.md"
    user_skill.parent.mkdir(parents=True)
    user_skill.write_text("user skill")
    monkeypatch.chdir(project)
    with patch("kb_core.__main__.Path.home", return_value=home):
        monkeypatch.setattr(sys, "argv", ["kb-core", "install", "--project", "--platform", "codex"])
        main()
        monkeypatch.setattr(sys, "argv", ["kb-core", "uninstall", "--project", "--platform", "codex"])
        main()
    assert user_skill.exists()
    assert not (project / ".codex" / "skills" / "kb-core" / "SKILL.md").exists()
    assert not (project / "AGENTS.md").exists()


def test_uninstall_project_without_platform_removes_project_installs(tmp_path, monkeypatch):
    from kb_core.__main__ import main
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    user_skill = home / ".claude" / "skills" / "kb-core" / "SKILL.md"
    user_skill.parent.mkdir(parents=True)
    user_skill.write_text("user skill")
    monkeypatch.chdir(project)
    with patch("kb_core.__main__.Path.home", return_value=home):
        monkeypatch.setattr(sys, "argv", ["kb-core", "install", "--project"])
        main()
        monkeypatch.setattr(sys, "argv", ["kb-core", "uninstall", "--project"])
        main()
    assert user_skill.exists()
    assert not (project / ".claude" / "skills" / "kb-core" / "SKILL.md").exists()
    assert not (project / ".claude" / "CLAUDE.md").exists()


# --- always-on AGENTS.md install/uninstall tests (Codex) ---


def test_remove_marker_section_matches_exact_heading_only(tmp_path):
    """#2062: the strip helper must match kb-core's own `## kb-core` heading
    exactly, never a substring inside a user's `### kb-core` H3."""
    from kb_core.install import _remove_marker_section
    m = "## kb-core"

    # Only a user H3 mention -> no exact marker line -> None (file left untouched).
    assert _remove_marker_section("# Doc\n\n### kb-core\n\nmy notes\n", m) is None
    # An inline/bullet mention is likewise not a section.
    assert _remove_marker_section("see the ## kb-core bullet\n", m) is None

    # A real H2 section alongside a user H3: remove only the H2 section.
    content = "# Doc\n\n### kb-core\n\nmy notes\n\n## kb-core\n\nkb_core stuff\n"
    out = _remove_marker_section(content, m)
    assert out is not None
    assert "### kb-core" in out and "my notes" in out
    assert not any(l.strip() == "## kb-core" for l in out.splitlines())
    assert "kb-core stuff" not in out

    # The section runs to the next H2 (not stopping at a `###` inside it).
    c2 = "## kb-core\n\nintro\n\n### sub\n\ninner\n\n## Keep\n\nkeep me\n"
    out2 = _remove_marker_section(c2, m)
    assert "## Keep" in out2 and "keep me" in out2
    assert "inner" not in out2 and "intro" not in out2


def test_codex_agents_install_writes_agents_md(tmp_path):
    from kb_core.__main__ import _codex_agents_md_install

    _codex_agents_md_install(tmp_path)
    agents_md = tmp_path / "AGENTS.md"
    assert agents_md.exists()
    assert "kb-core" in agents_md.read_text()
    assert "GRAPH_REPORT.md" in agents_md.read_text()


def test_agents_install_idempotent(tmp_path):
    """Installing twice does not duplicate the section."""
    from kb_core.__main__ import _codex_agents_md_install

    _codex_agents_md_install(tmp_path)
    _codex_agents_md_install(tmp_path)
    content = (tmp_path / "AGENTS.md").read_text()
    assert content.count("## kb-core") == 1


def test_agents_install_appends_to_existing(tmp_path):
    """Installs into an existing AGENTS.md without overwriting other content."""
    from kb_core.__main__ import _codex_agents_md_install

    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("# Existing rules\n\nDo not break things.\n")
    _codex_agents_md_install(tmp_path)
    content = agents_md.read_text()
    assert "Do not break things." in content
    assert "## kb-core" in content


def test_agents_uninstall_removes_section(tmp_path):
    from kb_core.__main__ import _codex_agents_md_install, _codex_agents_md_uninstall

    _codex_agents_md_install(tmp_path)
    _codex_agents_md_uninstall(tmp_path)
    agents_md = tmp_path / "AGENTS.md"
    # File deleted when it only contained kb_core section
    assert not agents_md.exists()


def test_agents_uninstall_preserves_other_content(tmp_path):
    """Uninstall keeps pre-existing content."""
    from kb_core.__main__ import _codex_agents_md_install, _codex_agents_md_uninstall

    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("# Existing rules\n\nDo not break things.\n")
    _codex_agents_md_install(tmp_path)
    _codex_agents_md_uninstall(tmp_path)
    assert agents_md.exists()
    content = agents_md.read_text()
    assert "Do not break things." in content
    assert "## kb-core" not in content


def test_agents_uninstall_no_op_when_not_installed(tmp_path, capsys):
    from kb_core.__main__ import _codex_agents_md_uninstall

    _codex_agents_md_uninstall(tmp_path)
    out = capsys.readouterr().out
    assert "nothing to do" in out


def test_agents_uninstall_preserves_user_h3_kb_core_heading(tmp_path):
    """#2062 end-to-end: uninstall strips kb-core's own H2 section but leaves a
    user-authored `### kb-core` H3 (and everything else) byte-intact."""
    from kb_core.__main__ import _codex_agents_md_install, _codex_agents_md_uninstall

    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text(
        "# My rules\n\n"
        "### kb-core\n\n"
        "My own notes on how I use kb_core. Keep this.\n\n"
        "## Other\n\nUnrelated content.\n"
    )
    _codex_agents_md_install(tmp_path)  # appends a genuine `## kb_core` H2 section
    assert "## kb-core" in agents_md.read_text()

    _codex_agents_md_uninstall(tmp_path)
    content = agents_md.read_text()
    assert "### kb-core" in content, "user's H3 heading was deleted (#2062)"
    assert "My own notes on how I use kb_core. Keep this." in content
    assert "## Other" in content and "Unrelated content." in content
    assert not any(l.strip() == "## kb-core" for l in content.splitlines())


def test_uninstall_untouched_when_only_user_h3_present(tmp_path, capsys):
    """#2062: a file with only a user `### kb-core` H3 (kb-core never installed)
    must be left byte-identical, not stripped."""
    from kb_core.__main__ import _codex_agents_md_uninstall

    agents_md = tmp_path / "AGENTS.md"
    original = "# My rules\n\n### kb-core\n\nHand-written. Do not touch.\n"
    agents_md.write_text(original)
    before = agents_md.read_bytes()
    _codex_agents_md_uninstall(tmp_path)
    assert agents_md.read_bytes() == before
    assert "nothing to do" in capsys.readouterr().out


def _cli_dispatched_commands() -> set[str]:
    """Subcommand names the CLI actually dispatches.

    `kb-core`'s dispatcher is an `elif cmd == "..."` chain rather than a declarative
    table, so the set is read back out of the source. Used to prove a hook command
    written by an installer is not a stale/renamed subcommand (#2165).
    """
    import re
    from kb_core import cli

    source = Path(cli.__file__).read_text(encoding="utf-8")
    names = set(re.findall(r'cmd\s*==\s*"([a-z0-9][a-z0-9-]*)"', source))
    names |= {
        m
        for group in re.findall(r'cmd\s+in\s+\(([^)]*)\)', source)
        for m in re.findall(r'"([a-z0-9][a-z0-9-]*)"', group)
    }
    return names


def test_codex_hook_command_is_a_real_cli_subcommand(tmp_path):
    """#2165: the PreToolUse command in .codex/hooks.json must be a command the CLI
    dispatches, so a renamed subcommand can never leave a permanently dead hook.

    `hook-check` is intentionally a no-op on Codex (Codex Desktop rejects
    additionalContext on PreToolUse), but it must still be a *recognized* command --
    an unrecognized one exits non-zero and would break every Bash tool call.
    """
    import json

    from kb_core.install import _install_codex_hook

    _install_codex_hook(tmp_path)
    hooks = json.loads((tmp_path / ".codex" / "hooks.json").read_text(encoding="utf-8"))

    entries = [
        h
        for group in hooks["hooks"]["PreToolUse"]
        for h in group["hooks"]
        if "kb-core" in h.get("command", "")
    ]
    assert entries, "codex install must register a kb-core PreToolUse hook"

    dispatched = _cli_dispatched_commands()
    assert "hook-check" in dispatched, "sanity: parser must find known commands"

    for entry in entries:
        # command is "<abs exe path> <subcommand> [args...]"
        parts = entry["command"].split()
        subcommand = parts[1] if len(parts) > 1 else ""
        assert subcommand in dispatched, (
            f"codex hook registers {subcommand!r}, which the CLI does not dispatch "
            f"(#2165). Known commands: {sorted(dispatched)}"
        )
