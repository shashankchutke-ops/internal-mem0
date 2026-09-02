#!/bin/sh
set -eu

MCP_NAME="mem0-self-hosted"
DEFAULT_API_URL="https://mem0.shashawk.com"
DEFAULT_AGENT_ID="mem0-client"
DEFAULT_KEYCHAIN_SERVICE="mem0-self-hosted-api-key"

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$script_dir
launcher="$project_dir/bin/mem0-mcp-macos"

dry_run=0
name_input=""
user_id_override=""
api_url="${MEM0_API_URL:-$DEFAULT_API_URL}"
agent_id="${MEM0_AGENT_ID:-$DEFAULT_AGENT_ID}"
keychain_service="${MEM0_KEYCHAIN_SERVICE:-$DEFAULT_KEYCHAIN_SERVICE}"
keychain_account="${MEM0_KEYCHAIN_ACCOUNT:-${USER:-}}"

die() {
    echo "Error: $*" >&2
    exit 1
}

warn() {
    echo "Warning: $*" >&2
}

usage() {
    cat >&2 <<'EOF'
Usage: ./setup.sh [options]

Options:
  --name NAME       Teammate name; prompted for when omitted
  --user-id ID      Override the name-derived Mem0 namespace
  --api-url URL     Mem0 API URL (default: https://mem0.shashawk.com)
  --agent-id ID     Agent label (default: mem0-client)
  --dry-run         Show the setup without changing the machine
  -h, --help        Show this help

The API key is read silently and stored in macOS Keychain. It is never put in
the MCP configuration or written to this repository.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --name)
            [ "$#" -ge 2 ] || die "--name requires a value"
            name_input=$2
            shift 2
            ;;
        --user-id)
            [ "$#" -ge 2 ] || die "--user-id requires a value"
            user_id_override=$2
            shift 2
            ;;
        --api-url)
            [ "$#" -ge 2 ] || die "--api-url requires a value"
            api_url=$2
            shift 2
            ;;
        --agent-id)
            [ "$#" -ge 2 ] || die "--agent-id requires a value"
            agent_id=$2
            shift 2
            ;;
        --dry-run)
            dry_run=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "unknown option: $1"
            ;;
    esac
done

if [ -z "$name_input" ]; then
    if [ "$dry_run" -eq 1 ] && [ ! -t 0 ]; then
        IFS= read -r name_input || true
    else
        printf "Teammate name: " >&2
        IFS= read -r name_input || true
    fi
fi
[ -n "$name_input" ] || die "a teammate name is required"

slug=$(printf '%s' "$name_input" | LC_ALL=C tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//')
[ -n "$slug" ] || die "the name must contain at least one letter or number"

user_id="${MEM0_USER_ID:-${user_id_override:-$slug}}"
[ -n "$user_id" ] || die "Mem0 user ID must not be empty"
[ -n "$agent_id" ] || die "Mem0 agent ID must not be empty"
[ -n "$api_url" ] || die "Mem0 API URL must not be empty"

if [ "$dry_run" -eq 1 ]; then
    echo "Dry run; no changes made."
    echo "MEM0_API_URL=$api_url"
    echo "MEM0_USER_ID=$user_id"
    echo "MEM0_AGENT_ID=$agent_id"
    echo "Would store the API key in macOS Keychain service '$keychain_service'."
    echo "Would run: uv sync --project $project_dir"
    echo "Would configure Claude Code as user-scoped server '$MCP_NAME'."
    echo "Would configure Codex as user-scoped server '$MCP_NAME'."
    exit 0
fi

case "$(uname -s)" in
    Darwin) ;;
    *) die "this setup script is for macOS (Darwin)" ;;
esac

if ! command -v uv >/dev/null 2>&1; then
    if command -v brew >/dev/null 2>&1; then
        echo "uv is not installed; installing it with Homebrew..."
        brew install uv
    else
        die "uv is required. Install it from https://docs.astral.sh/uv/ or install Homebrew first."
    fi
fi

if ! command -v security >/dev/null 2>&1; then
    die "macOS security command is unavailable"
fi
[ -n "$keychain_account" ] || die "USER or MEM0_KEYCHAIN_ACCOUNT must be set"

if [ -n "${MEM0_API_KEY:-}" ]; then
    api_key=$MEM0_API_KEY
else
    printf "Mem0 API key (input hidden): " >&2
    IFS= read -r -s api_key || true
    printf '\n' >&2
fi
[ -n "$api_key" ] || die "an API key is required"

security add-generic-password \
    -a "$keychain_account" \
    -s "$keychain_service" \
    -w "$api_key" \
    -U
unset api_key MEM0_API_KEY

chmod +x "$launcher"
uv sync --project "$project_dir"

configure_claude() {
    claude_command="${MEM0_CLAUDE_COMMAND:-claude}"
    if ! command -v "$claude_command" >/dev/null 2>&1; then
        warn "Claude Code command '$claude_command' was not found; skipping Claude setup."
        return 0
    fi

    if "$claude_command" mcp get "$MCP_NAME" >/dev/null 2>&1; then
        echo "Claude Code already has '$MCP_NAME'; leaving its existing configuration unchanged."
        return 0
    fi

    "$claude_command" mcp add \
        --scope user \
        --transport stdio \
        "$MCP_NAME" \
        --env "MEM0_API_URL=$api_url" \
        --env "MEM0_USER_ID=$user_id" \
        --env "MEM0_AGENT_ID=$agent_id" \
        -- \
        "$launcher"
}

configure_codex() {
    if ! command -v codex >/dev/null 2>&1; then
        warn "Codex command was not found; skipping Codex setup."
        return 0
    fi

    if codex mcp get "$MCP_NAME" >/dev/null 2>&1; then
        echo "Codex already has '$MCP_NAME'; leaving its existing configuration unchanged."
        return 0
    fi

    codex mcp add "$MCP_NAME" \
        --env "MEM0_API_URL=$api_url" \
        --env "MEM0_USER_ID=$user_id" \
        --env "MEM0_AGENT_ID=$agent_id" \
        -- \
        "$launcher"
}

configure_claude
configure_codex

echo "Mem0 setup complete for namespace '$user_id'."
echo "Restart Claude Code and Codex, then verify with /mcp, 'claude mcp list', and 'codex mcp list'."
