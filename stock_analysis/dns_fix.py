"""
DNS fix for financial APIs that redirect to subdomains unreachable
from certain Chinese ISPs. Patches socket.getaddrinfo at startup.

Problem: web.ifzq.gtimg.cn -> 301 -> web3.ifzq.gtimg.cn (SSL cert mismatch)
Fix: map web3 -> web so it resolves to the correct IP
"""
import socket
import logging
from functools import wraps

logger = logging.getLogger("dns_fix")

# Hosts that need DNS override: {unreachable_host: reachable_host_to_resolve}
FIXED_HOSTS = {
    "web3.ifzq.gtimg.cn": "web.ifzq.gtimg.cn",  # BUGFIX
}

_cache: dict[str, list[tuple]] = {}


def _resolve_fixed(host: str, port: int, family: int) -> list[tuple] | None:
    if host not in FIXED_HOSTS:
        return None
    source = FIXED_HOSTS[host]
    try:
        original = socket.getaddrinfo(source, port, family, socket.SOCK_STREAM)
        fixed = [(fam, typ, proto, canon, (ip, p)) for fam, typ, proto, canon, (ip, p) in original]
        logger.info("DNS fix: %s -> %s (%s)", host, source, fixed[0][4][0] if fixed else "?")
        return fixed
    except Exception:
        return None


_original_getaddrinfo = socket.getaddrinfo


@wraps(_original_getaddrinfo)
def _patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if isinstance(host, str):
        fixed = _resolve_fixed(host, port, family)
        if fixed is not None:
            return fixed
    return _original_getaddrinfo(host, port, family, type, proto, flags)


def apply():
    """Apply DNS fix. Call once at startup."""
    socket.getaddrinfo = _patched_getaddrinfo
    logger.info("DNS fix applied for: %s", ", ".join(FIXED_HOSTS))
