from __future__ import annotations

import os
import subprocess
from pathlib import Path


MCP_ROOT = Path(__file__).parents[1]
SETUP_SCRIPT = MCP_ROOT / "setup.sh"


def test_setup_dry_run_normalizes_name_and_configures_both_clients() -> None:
    environment = os.environ.copy()
    environment.pop("MEM0_USER_ID", None)
    environment.pop("MEM0_AGENT_ID", None)

    result = subprocess.run(
        [str(SETUP_SCRIPT), "--dry-run"],
        input="Alice Smith\n",
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "MEM0_USER_ID=alice-smith" in result.stdout
    assert "MEM0_AGENT_ID=mem0-client" in result.stdout
    assert "Would configure Claude Code" in result.stdout
    assert "Would configure Codex" in result.stdout
    assert "MEM0_API_KEY" not in result.stdout
