import secrets
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import hmac
import hashlib

class CustomCSRFMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, secret: str, cookie_name: str = "csrftoken", header_name: str = "X-CSRF-Token"):
        super().__init__(app)
        self.secret = secret.encode()
        self.cookie_name = cookie_name
        self.header_name = header_name
        self.safe_methods = {"GET", "HEAD", "OPTIONS", "TRACE"}

    async def dispatch(self, request: Request, call_next):
        csrf_token = request.cookies.get(self.cookie_name)
        
        # If no token in cookie, generate one
        if not csrf_token:
            csrf_token = secrets.token_urlsafe(32)
            request.scope["csrf_token_new"] = csrf_token
        
        request.scope["csrf_token"] = csrf_token

        if request.method not in self.safe_methods:
            header_token = request.headers.get(self.header_name)
            
            # Simple comparison for now, can be improved with HMAC if needed
            if not header_token or not csrf_token or header_token != csrf_token:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF token missing or invalid"}
                )

        response = await call_next(request)

        # If a new token was generated, set it in the cookie
        if "csrf_token_new" in request.scope:
            response.set_cookie(
                self.cookie_name, 
                request.scope["csrf_token_new"], 
                httponly=True, 
                samesite="lax"
            )
            
        return response
