import time
import logging
from collections import deque
from starlette.types import ASGIApp, Scope, Receive, Send
from starlette.requests import Request
from starlette.responses import JSONResponse, HTMLResponse
from jinja2 import Environment, FileSystemLoader
import os

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tiered rate limit rules
# Each rule: (method, path_prefix, max_requests, window_seconds, context_message)
# Rules are checked in order — first match wins.
# ---------------------------------------------------------------------------
RATE_LIMIT_RULES: list[tuple[str | None, str, int, int, str]] = [
    # Auth endpoints — strictest (5 attempts per 60s)
    (
        "POST",
        "/auth/login",
        5,
        60,
        "Too many login attempts. For your security, please wait before trying again.",
    ),
    (
        "POST",
        "/auth/verify-otp",
        5,
        60,
        "Too many OTP attempts. Please wait before requesting another code.",
    ),
    # Checkout / order submission (10 per 60s)
    (
        "POST",
        "/checkout/",
        10,
        60,
        "You've placed too many orders in a short time. Please wait a moment before trying again.",
    ),
    # Global fallback (120 per 60s)
    (
        None,
        "/",
        120,
        60,
        "You've sent too many requests. Please slow down and try again shortly.",
    ),
]


def _get_client_ip(scope: Scope) -> str:
    """Extract the real client IP, honoring X-Forwarded-For for proxied setups."""
    headers = dict(scope.get("headers", []))
    forwarded_for = headers.get(b"x-forwarded-for", b"").decode()
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    client = scope.get("client")
    return client[0] if client else "unknown"


def _match_rule(method: str, path: str) -> tuple[int, int, str] | None:
    """Return (max_requests, window_seconds, context_message) for the first matching rule."""
    for rule_method, rule_prefix, max_req, window, message in RATE_LIMIT_RULES:
        method_matches = rule_method is None or rule_method == method
        path_matches = path == rule_prefix or path.startswith(rule_prefix)
        if method_matches and path_matches:
            return max_req, window, message
    return None


class RateLimitMiddleware:
    """
    Sliding-window in-memory rate limiter.

    Stores a deque of request timestamps per (ip, rule_prefix) key.
    On each request it evicts timestamps outside the window, then checks
    the count against the limit.

    Thread-safety note: asyncio is single-threaded, so dict mutations are safe
    without locks in a single-worker uvicorn setup.
    """

    def __init__(self, app: ASGIApp, template_dir: str | None = None):
        self.app = app
        # { (ip, path_prefix): deque([timestamp, ...]) }
        self._store: dict[tuple[str, str], deque] = {}

        # We render the 429 template manually (without FastAPI's DI) because
        # the middleware sits below the router layer.
        if template_dir is None:
            template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
        self._jinja_env = Environment(
            loader=FileSystemLoader(os.path.abspath(template_dir)),
            autoescape=True,
        )

    def _is_rate_limited(
        self, ip: str, path_prefix: str, max_requests: int, window: int
    ) -> tuple[bool, int]:
        """
        Returns (is_limited, retry_after_seconds).
        Mutates the store: evicts old timestamps and appends current one if allowed.
        """
        now = time.time()
        key = (ip, path_prefix)

        if key not in self._store:
            self._store[key] = deque()

        bucket = self._store[key]

        # Evict timestamps outside the window
        while bucket and now - bucket[0] > window:
            bucket.popleft()

        if len(bucket) >= max_requests:
            # Calculate how many seconds until the oldest entry expires
            retry_after = int(window - (now - bucket[0])) + 1
            return True, retry_after

        bucket.append(now)
        return False, 0

    async def _send_429(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        retry_after: int,
        context_message: str,
        is_htmx: bool,
    ) -> None:
        """Send a 429 response — HTML for browsers, JSON for HTMX/API clients."""
        headers_dict = dict(scope.get("headers", []))
        ip = _get_client_ip(scope)
        path = scope.get("path", "/")

        logger.warning(
            f"Rate limit exceeded — ip={ip} path={path} retry_after={retry_after}s"
        )

        extra_headers = [
            (b"retry-after", str(retry_after).encode()),
            (b"x-ratelimit-limit", b"exceeded"),
        ]

        if is_htmx:
            # HTMX expects an HTML fragment or a redirect trigger
            body = (
                f'<div class="text-danger text-sm font-medium py-2">'
                f"⏳ {context_message} Please wait {retry_after}s."
                f"</div>"
            ).encode()
            response = HTMLResponse(
                content=body.decode(),
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )
        elif headers_dict.get(b"accept", b"").startswith(b"application/json"):
            response = JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests",
                    "message": context_message,
                    "retry_after": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )
        else:
            # Full-page HTML response using the 429.html template
            try:
                tmpl = self._jinja_env.get_template("429.html")
                # Build a minimal fake request context for Jinja2
                # (base.html needs 'request' for csrf_token and url checks)
                request = Request(scope, receive)
                html = tmpl.render(
                    request=request,
                    retry_after=retry_after,
                    context_message=context_message,
                    csrf_token=scope.get("csrf_token", ""),
                )
            except Exception:
                # Fallback plain HTML if template rendering fails
                html = (
                    f"<h1>Too Many Requests</h1>"
                    f"<p>{context_message}</p>"
                    f"<p>Please try again in {retry_after} seconds.</p>"
                )
            response = HTMLResponse(
                content=html,
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )

        await response(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        path = scope.get("path", "/")
        headers_dict = dict(scope.get("headers", []))
        is_htmx = b"hx-request" in headers_dict

        match = _match_rule(method, path)
        if match is None:
            await self.app(scope, receive, send)
            return

        max_requests, window, context_message = match
        # Find the matching prefix for the store key
        rule_prefix = next(
            rp
            for _, rp, _, _, _ in RATE_LIMIT_RULES
            if path == rp or path.startswith(rp)
        )

        ip = _get_client_ip(scope)
        limited, retry_after = self._is_rate_limited(
            ip, rule_prefix, max_requests, window
        )

        if limited:
            await self._send_429(
                scope, receive, send, retry_after, context_message, is_htmx
            )
            return

        await self.app(scope, receive, send)
