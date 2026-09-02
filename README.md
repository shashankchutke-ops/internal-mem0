# Internal Mem0

This repository contains the complete local deployment used by the team:

- `server/` — standalone Mem0 API, dashboard, PostgreSQL/pgvector Compose stack,
  migrations, and the embedder-dimension write fix.
- `bin/` and the root Python package — a local stdio MCP bridge for Claude Code
  and Codex.

## Self-hosted server

Run the server from the cloned repository:

```bash
cd ~/src/internal-mem0/server
cp .env.example .env
```

Edit `.env` and set `POSTGRES_PASSWORD`, `JWT_SECRET`, and the API key for the
LLM/embedder provider you use. Then start the API, dashboard, and private
PostgreSQL/pgvector service:

```bash
docker compose up -d --build
```

The local endpoints are:

```text
API:       http://localhost:8888
Dashboard: http://localhost:3000
```

The Compose file does not publish PostgreSQL to the host. If using Cloudflare
Tunnel, route the API hostname to `http://localhost:8888` and the dashboard
hostname to `http://localhost:3000`; do not route the database. For a fresh
install, use `make bootstrap` or complete the browser setup at the dashboard.

The API normalizes the bundled embedder output to the pgvector column dimension
when no dimension is explicitly configured, so changing providers through the
dashboard does not leave reads working while writes fail with a vector-size
mismatch. See [`server/README.md`](server/README.md) for server operations,
backups, and production notes.

## MCP bridge for Claude Code and Codex

This package is a local stdio MCP bridge for the self-hosted Mem0 REST API. It
keeps the API key in macOS Keychain and sends requests to the configured Mem0
API over HTTPS. The included setup script configures Claude Code and Codex with
the same default `MEM0_AGENT_ID` (`mem0-client`).

The memory namespace is controlled by `MEM0_USER_ID`. The setup script derives
it from each teammate's name, which keeps new installations private by
default. Use an explicitly shared ID when a team wants one common namespace.

## Teammate setup

Clone this repository on the MacBook, then run the setup script:

```bash
git clone https://github.com/shashankchutke-ops/internal-mem0.git ~/src/internal-mem0
cd ~/src/internal-mem0
./setup.sh
```

The script will:

1. Prompt for the teammate's name and derive a slug such as `alice-smith`.
2. Read the Mem0 API key without echoing it and store it in macOS Keychain.
3. Install the bridge with `uv`.
4. Add a user-scoped server to Claude Code and Codex.

The key is never written to this repository or either MCP configuration. Each
client reads it from Keychain when it starts the bridge.

To intentionally share one namespace with trusted teammates, use the same
explicit ID on every MacBook:

```bash
./setup.sh --user-id juner-team
```

To inspect the derived values without changing the MacBook:

```bash
./setup.sh --dry-run
```

The current self-hosted REST API authenticates the API key but does not enforce
that the key owner may access only one `user_id`. Name-derived IDs are
therefore a privacy-by-convention setup for MCP clients, not a hard namespace
ACL against a caller that can invoke the REST API directly. Use the shared ID
only with teammates who are trusted with the same Mem0 API key, or add server
side per-namespace authorization before treating namespaces as security
boundaries.

## Server requirements

Create a per-user API key in the Mem0 dashboard at
`https://mem.shashawk.com/dashboard/api-keys`. The self-hosted server uses the
`X-API-Key` header and its REST paths do not have a `/v1` prefix.

For a public deployment, set `AUTH_DISABLED=false` in the server's untracked
`.env`, ensure `JWT_SECRET` is set, and restart the API. `AUTH_DISABLED=true`
is only appropriate for local development.

The default API URL is:

```text
https://mem0.shashawk.com
```

Override it during setup when needed:

```bash
./setup.sh --api-url https://mem0.example.com
```

## Manual macOS setup

The script is recommended, but the equivalent manual setup is:

```bash
brew install uv
cd /absolute/path/to/internal-mem0
uv sync
chmod +x bin/mem0-mcp-macos
```

Store the API key in the macOS Keychain. The prompt is silent:

```bash
read -r -s MEM0_API_KEY
printf '\\n'
security add-generic-password \
  -a "$USER" \
  -s mem0-self-hosted-api-key \
  -w "$MEM0_API_KEY" \
  -U
unset MEM0_API_KEY
```

The service name and account can be changed with `MEM0_KEYCHAIN_SERVICE` and
`MEM0_KEYCHAIN_ACCOUNT`.

## Configure Claude Code

Use the absolute path to the launcher. The server name must come before the
`--env` options:

```bash
claude mcp add \
  --scope user \
  --transport stdio \
  mem0-self-hosted \
  --env MEM0_API_URL=https://mem0.shashawk.com \
  --env MEM0_USER_ID=alice-smith \
  --env MEM0_AGENT_ID=mem0-client \
  -- \
  /absolute/path/to/internal-mem0/bin/mem0-mcp-macos
```

For a shell alias such as `claude-arjun`, use the actual Claude executable in
the command or run the command from a shell that resolves the alias. A direct
example is:

```bash
claude-arjun mcp add \
  --scope user \
  --transport stdio \
  mem0-self-hosted \
  --env MEM0_API_URL=https://mem0.shashawk.com \
  --env MEM0_USER_ID=alice-smith \
  --env MEM0_AGENT_ID=mem0-client \
  -- \
  /absolute/path/to/internal-mem0/bin/mem0-mcp-macos
```

Check the user-scoped configuration with:

```bash
claude mcp get mem0-self-hosted
claude mcp list
```

Restart Claude Code, then `/mcp` should show the memory tools.

## Configure Codex

Use Codex's user-level MCP configuration so it applies across projects:

```bash
codex mcp add mem0-self-hosted \
  --env MEM0_API_URL=https://mem0.shashawk.com \
  --env MEM0_USER_ID=alice-smith \
  --env MEM0_AGENT_ID=mem0-client \
  -- \
  /absolute/path/to/internal-mem0/bin/mem0-mcp-macos
```

Check it with:

```bash
codex mcp get mem0-self-hosted
codex mcp list
```

The command deliberately does not pass `MEM0_API_KEY`: the launcher loads it
from Keychain. This keeps the secret out of `~/.codex/config.toml` and avoids
depending on whether the client forwards variables whose names contain `KEY`.

If you prefer to edit `~/.codex/config.toml`, the equivalent entry is:

```toml
[mcp_servers.mem0-self-hosted]
command = "/absolute/path/to/internal-mem0/bin/mem0-mcp-macos"

[mcp_servers.mem0-self-hosted.env]
MEM0_API_URL = "https://mem0.shashawk.com"
MEM0_USER_ID = "alice-smith"
MEM0_AGENT_ID = "mem0-client"
```

## Verify sharing

Restart both clients and ask each one to call `memory_search` for a distinctive
temporary phrase. Then ask one client to add a temporary memory and the other
to search for it. Delete the temporary memory by its returned ID afterwards.

For a shared namespace, both clients should find the same memory. The
`agent_id` field can still identify which client wrote it, even though the
default setup uses the same agent label for every client.

Recommended agent behavior:

- Search relevant memories before starting a task.
- Store durable preferences, decisions, and project context only.
- Never store passwords, API keys, tokens, cookies, or private credentials.
- Confirm a memory ID before using `memory_update` or `memory_delete`.

## Troubleshooting

- `401`: create a new API key, confirm `AUTH_DISABLED=false` has a valid
  `JWT_SECRET`, and replace the Keychain item.
- `No Mem0 API key found`: rerun the Keychain command with the same account and
  service names.
- `Failed to connect`: use an absolute launcher path, run `chmod +x`, and
  confirm `uv --version` works in the client-launched environment.
- Claude reports `missing required argument 'commandOrUrl'`: put
  `mem0-self-hosted` before the `--env` flags, as shown above, and keep `--`
  immediately before the launcher path.
- Requests still target `localhost`: remove the old Mem0 MCP entry or plugin,
  restart the client, and verify that the configured server is
  `mem0-self-hosted`.

The bridge uses the self-hosted REST routes directly; it does not send your
memory data to Mem0 Cloud.
