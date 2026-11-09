# pyMCP

A lightweight Python [MCP](https://modelcontextprotocol.io/) server built with [FastMCP](https://gofastmcp.com/) for exposing tools to MCP-compatible clients (for example, `llama-server` integrations).

The current implementation provides a DuckDuckGo web search tool and supports two transports:

- **`stdio`** — for local MCP clients that launch the server as a subprocess
- **`streamable-http`** — for HTTP-based deployments, typically behind a reverse proxy such as Nginx

## Features

- **MCP tool: `search_ddg`** — DuckDuckGo search with normalized results (`title`, `url`, `snippet`)
- **Validated configuration** — YAML config + `.env` loading with Pydantic models
- **Bearer authentication** — required for network transports (`Authorization: Bearer <API_KEY>`)
- **CORS support** — enabled for HTTP deployments
- **Filesystem-based tool discovery** — tools are loaded from the `tools/` directory via `FileSystemProvider`

## Project Structure

```text
.
├── main.py            # Entry point (stdio / streamable-http via Uvicorn)
├── config.py          # Configuration loading and validation
├── config.yaml        # MCP/server settings
├── middleware.py      # Raw ASGI Bearer authentication middleware
├── nginx.conf         # Complete Nginx reverse‑proxy configuration (see notes below)
├── tools/
│   ├── __init__.py
│   └── search_web.py  # search_ddg tool implementation
├── requirements.txt   # Pinned dependencies (freeze)
├── .env.template      # Environment variable template
├── LICENSE
└── README.md
```

## Requirements

- **Python 3.11+** (recommended; use a version compatible with `requirements.txt`)
- Network access to DuckDuckGo for the `search_ddg` tool

## Quick Start

### 1. Create a virtual environment and install dependencies

```bash
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

### 2. Configure environment variables

Create a local `.env` file from the template:

```bash
cp .env.template .env
```

Set your API key (required for `streamable-http`):

```env
API_KEY=your_secret_api_key
```

> **Note:** `.env` is ignored by git. Do not commit secrets and do not store `API_KEY` in `config.yaml`.

### 3. Review `config.yaml`

Default example:

```yaml
mcp_name: "web-tools"
mcp_transport: "streamable-http"   # "stdio" | "streamable-http"
host: "127.0.0.1"
port: 18080
path: "/"
```

### 4. Run the server

```bash
python main.py
```

On startup, the server logs the number of registered tools and their names.

## Configuration

Configuration is loaded from:

1. `.env` (by default, `load_config()` expects this file to exist)
2. `config.yaml`

`API_KEY` is read from the environment (`.env` / process environment) and injected into the validated config.

| Setting | Description |
|---|---|
| `mcp_name` | MCP server name (1–32 characters). |
| `mcp_transport` | Transport mode: `stdio` or `streamable-http`. |
| `host` | Bind address for HTTP mode. |
| `port` | TCP port for HTTP mode (`1–65535`). |
| `path` | HTTP mount path for the MCP app (must start with `/`). |
| `API_KEY` (env) | Required for non-`stdio` transports. |

**Validation behavior:**
- Unknown/extra fields in `config.yaml` are rejected.
- `API_KEY` is mandatory when `mcp_transport` is not `stdio`.
- The default loader requires a `.env` file unless `load_config()` is called differently in code.

## Running Modes

### `stdio`

Use this mode for local MCP clients that communicate over standard input/output.

```yaml
mcp_transport: "stdio"
```

### `streamable-http`

Use this mode to serve MCP over HTTP (for example, on `127.0.0.1:18080`).

Clients must include the Bearer token on HTTP requests:

```http
Authorization: Bearer <API_KEY>
```

`OPTIONS` preflight requests are allowed without authentication.

## Tool Reference

### `search_ddg`

Defined in [`tools/search_web.py`](tools/search_web.py).

Performs a DuckDuckGo search and returns a normalized list of results.

**Parameters**

| Name | Type | Constraints | Default | Description |
|---|---|---|---:|---|
| `query` | `string` | 1–500 chars (trimmed) | — | Search query. |
| `max_results` | `integer` | 1–25 | `5` | Maximum number of results to return. |

**Response shape**

```json
[
  {
    "title": "Result title",
    "url": "https://example.com",
    "snippet": "Short excerpt..."
  }
]
```

**Error/behavior notes**
- Invalid input (for example, an empty query after trimming) raises a tool error.
- Upstream search failures are handled defensively: the tool logs the error and returns an empty list instead of failing hard. This allows the client/model to decide whether to retry or use a fallback strategy.

## Reverse Proxy (Nginx)

The repository now includes a **complete** Nginx configuration (`nginx.conf`) that defines an upstream pool and a server block listening on the standard port.

```nginx
upstream mcp-server {
    server 127.0.0.1:18080;
    keepalive 16;
}

server {

    location ^~ /mcp {
        proxy_pass http://mcp-server;
        proxy_http_version 1.1;

        proxy_set_header Connection "";

        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_buffering off;
        proxy_cache off;
        proxy_request_buffering off;

        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;

        client_max_body_size 10m;
    }
}
```

### Important mapping note

- `config.yaml` sets `path: "/"` (the MCP app is mounted at the root).
- The Nginx `location` block above matches **`^/mcp`** prefix.
- If you keep `path: "/"` in `config.yaml`, Nginx will forward requests that *start with* `/mcp` to the backend, while the MCP application expects requests at the literal root `/`. Two options to resolve this:
  1. **Change `config.yaml` `path` to `/mcp`** (then update any client references accordingly).
  2. **Adjust the Nginx `location`** to `^~ /` (or remove the prefix) so that requests arriving at the server root are proxied unchanged to the backend.

In most deployments where the MCP server sits *behind* a reverse proxy, the proxy is the public entry point and the MCP app is configured with `path: "/"` (or whatever internal path the client expects). Choose the approach that matches your architecture.

The upstream uses port `18080`, which matches the default `port` in `config.yaml`. If you change the port, adjust both the upstream `server` directive and the `host`/`port` in `config.yaml`.

## Security Notes

- Keep `API_KEY` in `.env` or a secret manager; never commit it.
- Restrict network exposure (bind to `127.0.0.1`, use firewall rules, and/or place behind TLS-terminating Nginx).
- CORS is currently configured to allow all origins (`*`). For production deployments, restrict allowed origins to trusted clients.
- Review and update dependencies regularly.

## Development Notes

- Add new tools under `tools/` using FastMCP's `@tool` decorator.
- `main.py` uses `FileSystemProvider(..., reload=False)`, so tool changes require a server restart.
- There are currently no automated tests in the repository. Adding tests for config loading, auth middleware, and tool behavior is recommended as the project grows.

## License

This project is licensed under the terms of the [LICENSE](LICENSE) file.
