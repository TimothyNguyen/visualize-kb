import subprocess
import sys


def test_base_cli_and_server_import_without_langgraph() -> None:
    code = """
import importlib.abc
import sys

class BlockLangGraph(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'langgraph' or fullname.startswith('langgraph.'):
            raise ModuleNotFoundError("blocked optional dependency", name='langgraph')
        return None

sys.meta_path.insert(0, BlockLangGraph())
import kb_core_ui.cli.root
import kb_core_ui.server.app
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
