from __future__ import annotations

import os
import subprocess
import fcntl
import pty
import termios
from pathlib import Path


MCP_ROOT = Path(__file__).parents[1]
INSTALLER = MCP_ROOT / "install.sh"


def _write_executable(path: Path, contents: str) -> None:
    path.write_text(contents)
    path.chmod(0o755)


def test_installer_clones_and_forwards_setup_options(tmp_path: Path) -> None:
    assert INSTALLER.exists(), "the public bootstrap installer has not been added yet"

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    git_args = tmp_path / "git-args"
    setup_args = tmp_path / "setup-args"
    install_dir = tmp_path / "install"

    _write_executable(
        fake_bin / "git",
        """#!/bin/sh
set -eu
printf '%s\\n' "$@" > "$MEM0_TEST_GIT_ARGS"
[ "$1" = "clone" ]
install_dir=$7
mkdir -p "$install_dir"
printf '%s\\n' '#!/bin/sh' 'set -eu' 'printf "%s\\n" "$@" > "$MEM0_TEST_SETUP_ARGS"' > "$install_dir/setup.sh"
chmod +x "$install_dir/setup.sh"
""",
    )

    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "MEM0_INSTALL_DIR": str(install_dir),
            "MEM0_REPOSITORY_URL": "https://example.invalid/internal-mem0.git",
            "MEM0_BRANCH": "main",
            "MEM0_TEST_GIT_ARGS": str(git_args),
            "MEM0_TEST_SETUP_ARGS": str(setup_args),
        }
    )

    result = subprocess.run(
        [str(INSTALLER), "--user-id", "juner-team"],
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert install_dir.joinpath("setup.sh").exists()
    assert git_args.read_text().splitlines() == [
        "clone",
        "--depth",
        "1",
        "--branch",
        "main",
        "https://example.invalid/internal-mem0.git",
        str(install_dir),
    ]
    assert setup_args.read_text().splitlines() == ["--user-id", "juner-team"]


def test_installer_does_not_overwrite_non_repository_directory(tmp_path: Path) -> None:
    assert INSTALLER.exists(), "the public bootstrap installer has not been added yet"

    install_dir = tmp_path / "existing"
    install_dir.mkdir()
    sentinel = install_dir / "keep-me.txt"
    sentinel.write_text("local data")

    environment = os.environ.copy()
    environment["MEM0_INSTALL_DIR"] = str(install_dir)

    result = subprocess.run(
        [str(INSTALLER)],
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )

    assert result.returncode != 0
    assert "not a Git checkout" in result.stderr
    assert sentinel.read_text() == "local data"


def test_installer_uses_controlling_terminal_for_piped_setup(tmp_path: Path) -> None:
    assert INSTALLER.exists(), "the public bootstrap installer has not been added yet"

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    install_dir = tmp_path / "install"
    tty_result = tmp_path / "tty-result"

    _write_executable(
        fake_bin / "git",
        """#!/bin/sh
set -eu
install_dir=$7
mkdir -p "$install_dir"
printf '%s\\n' '#!/bin/sh' 'set -eu' '[ -t 0 ] || { echo not-a-tty > "$MEM0_TEST_TTY_RESULT"; exit 1; }' 'IFS= read -r value' 'printf "%s" "$value" > "$MEM0_TEST_TTY_RESULT"' > "$install_dir/setup.sh"
chmod +x "$install_dir/setup.sh"
""",
    )

    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "MEM0_INSTALL_DIR": str(install_dir),
            "MEM0_REPOSITORY_URL": "https://example.invalid/internal-mem0.git",
            "MEM0_TEST_TTY_RESULT": str(tty_result),
        }
    )

    master_fd, slave_fd = pty.openpty()
    os.write(master_fd, b"terminal-input\n")

    def set_controlling_terminal() -> None:
        os.setsid()
        fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)

    try:
        process = subprocess.Popen(
            [str(INSTALLER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=environment,
            pass_fds=(slave_fd,),
            preexec_fn=set_controlling_terminal,
        )
        os.close(slave_fd)
        stdout, stderr = process.communicate(input="", timeout=10)
    finally:
        os.close(master_fd)

    assert process.returncode == 0, f"stdout={stdout}\nstderr={stderr}"
    assert tty_result.read_text() == "terminal-input"


def test_readme_documents_public_bootstrap_command() -> None:
    readme = (MCP_ROOT / "README.md").read_text()

    assert (
        "curl -fsSL https://github.com/shashankchutke-ops/internal-mem0/raw/refs/heads/main/install.sh | sh" in readme
    )
