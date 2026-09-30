#!/usr/bin/env python3
"""Verify Nebius Contree / Sandboxes credentials."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator.contree_sandbox import check_contree


def main() -> None:
    status = check_contree()
    if status.get("connected"):
        print("Contree OK")
        print(f"  project: {status.get('project_id')}")
        print(f"  token:   {status.get('token_uuid')}")
        print(f"  mode:    {status.get('mode')}")
        return
    print("Contree not connected")
    print(f"  error: {status.get('error', 'unknown')}")
    sys.exit(1)


if __name__ == "__main__":
    main()
