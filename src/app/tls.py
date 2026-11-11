"""TLS 1.2+ enforcement and SSLContext helper (APAS-SR-001, SAD section 4.4)."""

import os
import ssl
from typing import Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

HSTS_HEADER = "max-age=31536000; includeSubDomains"


def is_tls_enforced() -> bool:
    """Return True if APAS_ENFORCE_TLS environment variable is set to a truthy value."""
    val = os.environ.get("APAS_ENFORCE_TLS", "").strip().lower()
    return val in ("1", "true", "yes", "on")


def build_tls_context(certfile: str | None = None, keyfile: str | None = None) -> ssl.SSLContext:
    """Create a server SSLContext enforcing TLS 1.2 as minimum version (SR-001)."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2

    if certfile and keyfile:
        context.load_cert_chain(certfile=certfile, keyfile=keyfile)

    return context


class TLSEnforcementMiddleware(BaseHTTPMiddleware):
    """Enforce HTTPS and attach HSTS headers when APAS_ENFORCE_TLS is enabled."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        enforce = is_tls_enforced()

        if enforce:
            proto = request.headers.get("x-forwarded-proto", request.url.scheme).lower()
            if proto != "https":
                # Redirect insecure requests to HTTPS
                https_url = request.url.replace(scheme="https")
                # Use 307 for POST/PUT to preserve method and body, 301 for GET/HEAD
                status_code = 301 if request.method in ("GET", "HEAD") else 307
                response = RedirectResponse(url=str(https_url), status_code=status_code)
                response.headers["Strict-Transport-Security"] = HSTS_HEADER
                return response

        response = await call_next(request)

        if enforce:
            response.headers["Strict-Transport-Security"] = HSTS_HEADER

        return response
