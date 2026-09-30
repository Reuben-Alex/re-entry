"""
Re-exec the current script with the project venv Python when present.

Call ensure_project_python() before importing orchestrator (needs py-solc-x).
"""
import os
import sys
from pathlib import Path


def ensure_project_python() -> None:
    """Use .venv/bin/python so dependencies from requirements.txt are available."""
    root = Path(__file__).resolve().parent.parent
    venv_python = root / ".venv" / "bin" / "python"
    if not venv_python.is_file():
        return
    try:
        current = Path(sys.executable).resolve()
    except OSError:
        return
    if current == venv_python.resolve():
        return
    os.execv(str(venv_python), [str(venv_python), *sys.argv])
