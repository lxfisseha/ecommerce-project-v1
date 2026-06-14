import secrets
from fastapi import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Scope, Receive, Send
import hmac
import hashlib
from urllib.parse import parse_qs

class CustomCSRFMiddleware:
    def __init__(
        self, 
        app: ASGIApp, 
        secret: str, 
        cookie_name: str = "csrftoken", 
        header_name: str = "X-CSRF-Token"
    ):
        self.app = app
        self.secret = secret.encode()
        self.cookie_name = cookie_name
        self.header_name = header_name
        self.safe_methods = {"GET", "HEAD", "OPTIONS", "TRACE"}

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        csrf_cookie_token = request.cookies.get(self.cookie_name)

        # 1. Handle Token Generation/Retrieval
        if not csrf_cookie_token:
            csrf_cookie_token = secrets.token_urlsafe(32)
            scope["csrf_token_new"] = csrf_cookie_token

        scope["csrf_token"] = csrf_cookie_token

        # 2. Handle Validation for Unsafe Methods
        if request.method not in self.safe_methods:
            header_token = request.headers.get(self.header_name)
            # Fallback: check query parameters
            if not header_token:
                header_token = request.query_params.get("csrf_token")

            if not header_token or header_token != csrf_cookie_token:
                # Need to check form data
                content_type = request.headers.get("Content-Type", "")
                if "application/x-www-form-urlencoded" in content_type:
                    # Read the body to check for token
                    body = await request.body()
                    params = parse_qs(body.decode())
                    header_token = header_token or params.get("csrf_token", [None])[0]

                    # IMPORTANT: Wrap receive so downstream can read the body again
                    async def receive_with_body() -> dict:
                        return {"type": "http.request", "body": body, "more_body": False}

                    receive = receive_with_body
                
                # Note: multipart/form-data body parsing is complex and not fully implemented
                # for CSRF here. Relying on header/query param fallback.

            if not header_token or header_token != csrf_cookie_token:
                response = JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF token missing or invalid"}
                )
                await response(scope, receive, send)
                return

        # 3. Define Send Wrapper to set cookie
        async def send_wrapper(message: dict):
            if message["type"] == "http.response.start":
                if "csrf_token_new" in scope:
                    # Manually add Set-Cookie header
                    headers = message.get("headers", [])
                    cookie_val = f"{self.cookie_name}={scope['csrf_token_new']}; Path=/; HttpOnly; SameSite=Lax"
                    headers.append([b"set-cookie", cookie_val.encode()])
                    message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)

