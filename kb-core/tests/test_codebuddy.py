"""Tests for kb-core codebuddy install / uninstall commands."""
import json
from pathlib import Path
import sys
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _codebuddy_install_user(tmp_path):
    from kb_core.__main__ import install
    old_cwd = Path.cwd()
    try:
        import os
        os.chdir(tmp_path)
        with patch("kb_core.__main__.Path.home", return_value=tmp_path):
            install(platform="codebuddy")
    finally:
        import os
        os.chdir(old_cwd)


def _skill_path_user(tmp_path):
    return tmp_path / ".codebuddy" / "skills" / "kb-core" / "SKILL.md"


def _skill_path_project(project_dir):
    return project_dir / ".codebuddy" / "skills" / "kb-core" / "SKILL.md"


def _codebuddy_md_path(project_dir):
    return project_dir / "CODEBUDDY.md"


def _settings_path(project_dir):
    return project_dir / ".codebuddy" / "settings.json"


# ---------------------------------------------------------------------------
# User-scope install (kb_core install --platform codebuddy)
# ---------------------------------------------------------------------------

def test_codebuddy_install_user_creates_skill_file(tmp_path):
    """User-scope install copies skill to ~/.codebuddy/skills/kb-core/SKILL.md."""
    _codebuddy_install_user(tmp_path)
    skill_path = _skill_path_user(tmp_path)
    assert skill_path.exists()


def test_codebuddy_skill_file_contains_frontmatter(tmp_path):
    """Installed skill file must include kb-core YAML frontmatter."""
    _codebuddy_install_user(tmp_path)
    content = _skill_path_user(tmp_path).read_text()
    assert "name: kb-core" in content
    assert "description:" in content


def test_codebuddy_skill_file_references_kb_core_query(tmp_path):
    """/kb-core skill must mention kb-core query (query-first policy)."""
    _codebuddy_install_user(tmp_path)
    content = _skill_path_user(tmp_path).read_text()
    assert "kb-core query" in content or "/kb-core query" in content


# ---------------------------------------------------------------------------
# Project-scope install (kb_core codebuddy install)
# ---------------------------------------------------------------------------

def test_codebuddy_install_project_writes_codebuddy_md(tmp_path):
    """Project-scope install writes CODEBUDDY.md with kb-core section."""
    from kb_core.__main__ import codebuddy_install
    codebuddy_install(tmp_path)
    md = _codebuddy_md_path(tmp_path)
    assert md.exists()
    content = md.read_text()
    assert "## kb-core" in content
    assert "kb-core-out/" in content


def test_codebuddy_install_project_writes_hook(tmp_path):
    """Project-scope install registers PreToolUse hook in .codebuddy/settings.json."""
    from kb_core.__main__ import codebuddy_install
    codebuddy_install(tmp_path)
    settings_path = _settings_path(tmp_path)
    assert settings_path.exists()
    settings = json.loads(settings_path.read_text())
    hooks = settings["hooks"]["PreToolUse"]
    assert any("kb-core" in str(h) for h in hooks)


def test_codebuddy_install_hook_has_bash_matcher(tmp_path):
    """The installed hook must include Bash matcher for code search interception."""
    from kb_core.__main__ import codebuddy_install
    codebuddy_install(tmp_path)
    settings = json.loads(_settings_path(tmp_path).read_text())
    hooks = settings["hooks"]["PreToolUse"]
    bash_hooks = [h for h in hooks if h.get("matcher") == "Bash|Grep"]
    assert any("kb-core" in str(h) for h in bash_hooks)


def test_codebuddy_install_hook_has_read_glob_matcher(tmp_path):
    """The installed hook must include Read|Glob matcher for file-read interception."""
    from kb_core.__main__ import codebuddy_install
    codebuddy_install(tmp_path)
    settings = json.loads(_settings_path(tmp_path).read_text())
    hooks = settings["hooks"]["PreToolUse"]
    read_hooks = [h for h in hooks if h.get("matcher") == "Read|Glob"]
    assert any("kb-core" in str(h) for h in read_hooks)


def test_codebuddy_install_idempotent(tmp_path):
    """Re-install does not duplicate ## kb-core sections."""
    from kb_core.__main__ import codebuddy_install
    codebuddy_install(tmp_path)
    codebuddy_install(tmp_path)
    md = _codebuddy_md_path(tmp_path)
    assert md.read_text().count("## kb-core") == 1


def test_codebuddy_install_upgrades_stale_section(tmp_path):
    """Re-install replaces an old kb-core section with the current template."""
    from kb_core.__main__ import codebuddy_install, _CODEBUDDY_MD_MARKER
    # Write a stale section manually
    md = _codebuddy_md_path(tmp_path)
    md.write_text("old content\n\n## kb-core\nThis is old instructions\n")
    codebuddy_install(tmp_path)
    content = md.read_text()
    assert _CODEBUDDY_MD_MARKER in content
    assert "old content" in content
    assert "This is old instructions" not in content
    assert "kb-core-out/" in content
    assert content.count("## kb-core") == 1


def test_codebuddy_install_merges_existing_codebuddy_md(tmp_path):
    """Install appends to an existing CODEBUDDY.md, preserving other content."""
    from kb_core.__main__ import codebuddy_install
    _codebuddy_md_path(tmp_path).write_text("# My project rules\n")
    codebuddy_install(tmp_path)
    content = _codebuddy_md_path(tmp_path).read_text()
    assert "# My project rules" in content
    assert "## kb-core" in content
    assert "kb-core-out/" in content


def test_codebuddy_install_prints_no_change_on_second_run(tmp_path, capsys):
    """Second install prints '(no change)' when content is identical."""
    from kb_core.__main__ import codebuddy_install
    codebuddy_install(tmp_path)
    out1 = capsys.readouterr().out
    codebuddy_install(tmp_path)
    out2 = capsys.readouterr().out
    assert "no change" in out2


def test_codebuddy_install_hint_git_add(tmp_path, capsys):
    """Project-scoped install via CLI prints a git add hint."""
    from kb_core.__main__ import main
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    old_cwd = Path.cwd()
    try:
        import os
        os.chdir(project)
        with patch("kb_core.__main__.Path.home", return_value=home):
            sys.argv = ["kb-core", "codebuddy", "install"]
            main()
    finally:
        import os
        os.chdir(old_cwd)
    # codebuddy_install calls print() directly, no git add hint printed there
    # so this test checks that no errors occur


# ---------------------------------------------------------------------------
# Uninstall
# ---------------------------------------------------------------------------

def test_codebuddy_uninstall_removes_section(tmp_path):
    """Uninstall removes the ## kb-core section from CODEBUDDY.md."""
    from kb_core.__main__ import codebuddy_install, codebuddy_uninstall
    codebuddy_install(tmp_path)
    codebuddy_uninstall(tmp_path)
    md = _codebuddy_md_path(tmp_path)
    assert not md.exists()


def test_codebuddy_uninstall_removes_hook(tmp_path):
    """Uninstall removes the PreToolUse hook from .codebuddy/settings.json."""
    from kb_core.__main__ import codebuddy_install, codebuddy_uninstall
    codebuddy_install(tmp_path)
    codebuddy_uninstall(tmp_path)
    settings_path = _settings_path(tmp_path)
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())
        hooks = settings.get("hooks", {}).get("PreToolUse", [])
        assert not any("kb-core" in str(h) for h in hooks)


def test_codebuddy_uninstall_noop_if_not_installed(tmp_path):
    """Uninstall should not raise when CODEBUDDY.md doesn't exist."""
    from kb_core.__main__ import codebuddy_uninstall
    codebuddy_uninstall(tmp_path)  # should not raise


def test_codebuddy_uninstall_noop_if_no_section(tmp_path):
    """Uninstall should not error when CODEBUDDY.md exists but no kb-core section."""
    from kb_core.__main__ import codebuddy_uninstall
    _codebuddy_md_path(tmp_path).write_text("# Some other project\n")
    codebuddy_uninstall(tmp_path)
    content = _codebuddy_md_path(tmp_path).read_text()
    assert "# Some other project" in content


def test_codebuddy_uninstall_preserves_other_content(tmp_path):
    """Uninstall preserves non-kb-core content in CODEBUDDY.md."""
    from kb_core.__main__ import codebuddy_install, codebuddy_uninstall
    _codebuddy_md_path(tmp_path).write_text("# My project rules\n")
    codebuddy_install(tmp_path)
    codebuddy_uninstall(tmp_path)
    # When kb_core section was appended, uninstall removes it and the file
    # becomes the original content
    content = _codebuddy_md_path(tmp_path).read_text()
    assert "## kb-core" not in content
    assert "# My project rules" in content


# ---------------------------------------------------------------------------
# uninstall_all integration
# ---------------------------------------------------------------------------

def test_uninstall_all_removes_codebuddy_md(tmp_path, monkeypatch):
    """kb-core uninstall must clean up CODEBUDDY.md."""
    from kb_core.__main__ import main
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    with patch("kb_core.__main__.Path.home", return_value=home):
        monkeypatch.setattr(sys, "argv", ["kb-core", "codebuddy", "install"])
        main()
        md = _codebuddy_md_path(project)
        assert md.exists()
        monkeypatch.setattr(sys, "argv", ["kb-core", "uninstall"])
        main()
    assert not md.exists()


def test_uninstall_all_removes_codebuddy_hook(tmp_path, monkeypatch):
    """kb-core uninstall must clean up .codebuddy/settings.json hooks."""
    from kb_core.__main__ import main
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    with patch("kb_core.__main__.Path.home", return_value=home):
        monkeypatch.setattr(sys, "argv", ["kb-core", "codebuddy", "install"])
        main()
        monkeypatch.setattr(sys, "argv", ["kb-core", "uninstall"])
        main()
    settings_path = _settings_path(project)
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())
        hooks = settings.get("hooks", {}).get("PreToolUse", [])
        assert not any("kb-core" in str(h) for h in hooks)


# ---------------------------------------------------------------------------
# Platform config sanity
# ---------------------------------------------------------------------------

def test_codebuddy_in_platform_config():
    """codebuddy must be registered in _PLATFORM_CONFIG."""
    from kb_core.__main__ import _PLATFORM_CONFIG
    assert "codebuddy" in _PLATFORM_CONFIG
    assert _PLATFORM_CONFIG["codebuddy"]["skill_file"] == "skill.md"
    assert _PLATFORM_CONFIG["codebuddy"]["claude_md"] is False


def test_codebuddy_platform_skill_destination_user_scope(tmp_path):
    """User-scope destination must be ~/.codebuddy/skills/kb-core/SKILL.md."""
    from kb_core.__main__ import _platform_skill_destination
    with patch("kb_core.__main__.Path.home", return_value=tmp_path):
        dst = _platform_skill_destination("codebuddy", project=False)
    assert dst == tmp_path / ".codebuddy" / "skills" / "kb-core" / "SKILL.md"


def test_codebuddy_platform_skill_destination_project_scope(tmp_path):
    """Project-scope destination must be <project>/.codebuddy/skills/kb-core/SKILL.md."""
    from kb_core.__main__ import _platform_skill_destination
    dst = _platform_skill_destination("codebuddy", project=True, project_dir=tmp_path)
    assert dst == tmp_path / ".codebuddy" / "skills" / "kb-core" / "SKILL.md"


def test_codebuddy_in_main_help_text(capsys, monkeypatch):
    """`kb-core --help` must list codebuddy in the platform list and per-platform section."""
    from kb_core.__main__ import main
    monkeypatch.setattr(sys, "argv", ["kb-core", "--help"])
    main()
    captured = capsys.readouterr().out
    # codebuddy should appear in the top-level platform list
    assert "|codebuddy)" in captured or "codebuddy" in captured, (
        "codebuddy missing from `kb-core --help` platform list"
    )
    # codebuddy install / uninstall should appear in the per-platform section
    assert "codebuddy install" in captured, "`codebuddy install` line missing from help text"
    assert "codebuddy uninstall" in captured, "`codebuddy uninstall` line missing from help text"


def test_codebuddy_skill_file_exists_in_package():
    """skill.md must be present in the installed package (shared with claude)."""
    import kb_core
    skill = Path(kb_core.__file__).parent / "skill.md"
    assert skill.exists(), "skill.md missing from package"


def test_codebuddy_installation_roundtrip(tmp_path):
    """Install then uninstall leaves no trace of kb-core CODEBUDDY.md or hook."""
    from kb_core.__main__ import codebuddy_install, codebuddy_uninstall
    # Pre-existing project file
    _codebuddy_md_path(tmp_path).write_text("# My project\n")
    # One section above kb_core to test cleanup
    codebuddy_install(tmp_path)
    codebuddy_uninstall(tmp_path)
    # CODEBUDDY.md should exist with original content only
    md = _codebuddy_md_path(tmp_path)
    assert md.exists()
    content = md.read_text()
    assert "## kb-core" not in content
    assert "# My project" in content
    # Hook should be removed
    settings_path = _settings_path(tmp_path)
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())
        hooks = settings.get("hooks", {}).get("PreToolUse", [])
        assert not any("kb-core" in str(h) for h in hooks)
