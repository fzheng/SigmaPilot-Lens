"""Network security middleware for internal-only access."""

import ipaddress
from typing import List

from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware

from src.observability.logging import get_logger

logger = get_logger(__name__)

# Docker default bridge network ranges
ALLOWED_NETWORKS = [
    ipaddress.ip_network("172.16.0.0/12"),   # Docker default
    ipaddress.ip_network("192.168.0.0/16"),  # Docker custom
    ipaddress.ip_network("10.0.0.0/8"),      # Docker Swarm / overlay
    ipaddress.ip_network("127.0.0.0/8"),     # Localhost
]


def is_internal_ip(ip: str) -> bool:
    """
    Check if an IP address is from an internal/Docker network.

    Args:
        ip: IP address string

    Returns:
        True if the IP is from an allowed internal network
    """
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in network for network in ALLOWED_NETWORKS)
    except ValueError:
        logger.warning(f"Invalid IP address format: {ip}")
        return False


def get_client_ip(request: Request) -> str:
    """
    Extract client IP from request, checking forwarded headers.

    Args:
        request: FastAPI request object

    Returns:
        Client IP address string
    """
    # Check X-Forwarded-For header first (in case of reverse proxy)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Take the first IP in the chain (original client)
        return forwarded.split(",")[0].strip()

    # Check X-Real-IP header
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    # Fall back to direct client IP
    if request.client:
        return request.client.host

    return "unknown"


class InternalNetworkMiddleware(BaseHTTPMiddleware):
    """
    Middleware that restricts access to internal Docker network only.

    Rejects all requests from external IP addresses.
    """

    # Paths that are always allowed (for Docker health checks from host)
    ALLOWED_PATHS = [
        "/api/v1/health",
        "/api/v1/ready",
    ]

    async def dispatch(self, request: Request, call_next):
        client_ip = get_client_ip(request)
        path = request.url.path

        # Always allow health check endpoints
        if path in self.ALLOWED_PATHS:
            return await call_next(request)

        # Check if IP is from internal network
        if not is_internal_ip(client_ip):
            logger.warning(
                f"Rejected external request from {client_ip} to {path}",
                extra={"client_ip": client_ip, "path": path}
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": {
                        "code": "FORBIDDEN",
                        "message": "Access denied. This API is only accessible from internal network.",
                    }
                },
            )

        return await call_next(request)
