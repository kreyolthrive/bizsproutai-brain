"""
Hardened TLS transport for the Python backend.

The previous implementation advertised SPKI pinning but never accessed or
validated the peer certificate. This module now exposes only controls that are
actually enforced by httpx/OpenSSL: CA validation, hostname validation, and a
minimum TLS version.

True application-level certificate/SPKI pinning should only be added in a
runtime or proxy where the peer certificate is explicitly available and can be
validated against rotation-safe pins.
"""

import ssl

import httpx


def create_hardened_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def create_secure_async_client(timeout: float = 45.0) -> httpx.AsyncClient:
    """Return an AsyncClient using verified HTTPS with hardened TLS settings."""
    ssl_context = create_hardened_ssl_context()
    transport = httpx.AsyncHTTPTransport(verify=ssl_context)
    return httpx.AsyncClient(transport=transport, timeout=timeout)


# Compatibility alias for the existing OpenAI client wiring. Despite the old
# name, this function now provides verified/hardened TLS rather than claiming
# certificate pinning that the transport does not perform.
def create_pinned_async_client(timeout: float = 45.0, pinned_hosts=None) -> httpx.AsyncClient:
    del pinned_hosts
    return create_secure_async_client(timeout=timeout)
