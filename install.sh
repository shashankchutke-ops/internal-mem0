#!/bin/sh
set -eu

DEFAULT_REPOSITORY_URL="https://github.com/shashankchutke-ops/internal-mem0.git"
DEFAULT_BRANCH="main"
DEFAULT_INSTALL_DIR="${HOME:-.}/src/internal-mem0"

repository_url="${MEM0_REPOSITORY_URL:-$DEFAULT_REPOSITORY_URL}"
branch="${MEM0_BRANCH:-$DEFAULT_BRANCH}"
install_dir="${MEM0_INSTALL_DIR:-$DEFAULT_INSTALL_DIR}"

die() {
    echo "Error: $*" >&2
    exit 1
}

command -v git >/dev/null 2>&1 || die "git is required"
[ -n "$install_dir" ] || die "MEM0_INSTALL_DIR must not be empty"
[ -n "$repository_url" ] || die "MEM0_REPOSITORY_URL must not be empty"
[ -n "$branch" ] || die "MEM0_BRANCH must not be empty"

if [ -e "$install_dir" ]; then
    [ -d "$install_dir/.git" ] || die "install directory '$install_dir' exists but is not a Git checkout; choose another MEM0_INSTALL_DIR"

    remote_url=$(git -C "$install_dir" remote get-url origin 2>/dev/null) || die "install directory '$install_dir' has no origin remote"
    [ "$remote_url" = "$repository_url" ] || die "origin for '$install_dir' is '$remote_url', not '$repository_url'"

    current_branch=$(git -C "$install_dir" branch --show-current)
    [ "$current_branch" = "$branch" ] || die "install directory '$install_dir' is on '$current_branch', expected '$branch'"
    [ -z "$(git -C "$install_dir" status --porcelain)" ] || die "install directory '$install_dir' has local changes; commit or remove them before updating"

    git -C "$install_dir" pull --ff-only origin "$branch"
else
    mkdir -p "$(dirname "$install_dir")"
    git clone --depth 1 --branch "$branch" "$repository_url" "$install_dir"
fi

[ -f "$install_dir/setup.sh" ] || die "downloaded repository does not contain setup.sh"

if [ -r /dev/tty ] && ( : </dev/tty ) 2>/dev/null; then
    exec sh "$install_dir/setup.sh" "$@" </dev/tty
fi

exec sh "$install_dir/setup.sh" "$@"
