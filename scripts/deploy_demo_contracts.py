"""
Deploys challenge contracts from manifest to a local Anvil node.
"""
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS))
from ensure_venv import ensure_project_python

ensure_project_python()

sys.path.insert(0, str(_SCRIPTS.parent))

from orchestrator.setup import deploy_all


def main():
    deploy_all()


if __name__ == "__main__":
    main()
