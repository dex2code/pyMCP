import logging
from pathlib import Path

import anyio
from fastmcp import FastMCP
from fastmcp.server.providers import FileSystemProvider
import uvicorn
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from config import load_config
from middleware import BearerAuthMiddleware

TOOLS_DIR = Path(__file__).parent / "tools"

logger = logging.getLogger(__name__)

app_config = load_config()
mcp = FastMCP(
    app_config.mcp_name,
    providers=[
        FileSystemProvider(
            root=TOOLS_DIR,
            reload=False,
        )
    ],
)


def _build_http_app():
    """Wrap the MCP ASGI app with CORS + Bearer auth for public network access."""
    if app_config.api_key is None:
        # load_config already requires the key for network transports; this is
        # a defensive check so the type narrowing is explicit.
        raise RuntimeError(
            f"api_key is required for transport {app_config.mcp_transport!r}"
        )
    api_key = app_config.api_key.get_secret_value()

    middleware = [
        # CORS must be the OUTERMOST layer so preflight and 401 responses
        # also carry CORS headers. In Starlette, first item = outermost.
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,  # must be False when origins="*"
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
            allow_headers=[
                "Content-Type",
                "Authorization",
                "Mcp-Session-Id",
                "Mcp-Protocol-Version",
            ],
            expose_headers=["Mcp-Session-Id"],
        ),
        Middleware(BearerAuthMiddleware, api_key=api_key),
    ]

    return mcp.http_app(
        path=app_config.path,
        middleware=middleware,
    )


async def _log_registered_tools() -> None:
    tools = await mcp.list_tools()
    if not tools:
        logger.error(
            "No tools registered — check that %s exists and contains @tool-decorated functions",
            TOOLS_DIR,
        )
        return
    logger.info(
        "Registered %d tool(s): %s", len(tools), ", ".join(t.name for t in tools)
    )


async def main() -> None:
    await _log_registered_tools()

    if app_config.mcp_transport == "stdio":
        await mcp.run_stdio_async()
        return

    app = _build_http_app()
    config = uvicorn.Config(
        app,
        host=str(app_config.host),
        port=app_config.port,
        log_level="info",
    )
    await uvicorn.Server(config).serve()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    anyio.run(main)
