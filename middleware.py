class BearerAuthMiddleware:
    """Require 'Authorization: Bearer <key>' on every non-preflight HTTP request.

    Implemented as a raw ASGI middleware, not BaseHTTPMiddleware, because the
    latter buffers responses and breaks streaming for streamable-http and SSE.
    """

    def __init__(self, app, api_key: str) -> None:
        self.app = app
        self.api_key = api_key

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or scope["method"] == "OPTIONS":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        auth = headers.get(b"authorization", b"").decode("latin-1")

        if not auth.startswith("Bearer ") or auth[7:].strip() != self.api_key:
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"www-authenticate", b'Bearer realm="mcp"'),
                    ],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": b'{"error":"unauthorized"}',
                }
            )
            return

        await self.app(scope, receive, send)
