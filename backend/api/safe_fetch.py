"""Fetch a user-supplied web page without letting it reach internal services (SSRF guard).

``POST /recipes/import-url`` downloads whatever URL a user pastes. Unchecked, that
would let a user make the server request ``http://127.0.0.1:8001/...``, other
containers, the private network or the cloud metadata endpoint
(``169.254.169.254``), and read the response back via the imported recipe.

``fetch_page``:

- accepts only ``http``/``https`` URLs;
- resolves the host and refuses unless **every** address is publicly routable
  (no loopback, private, link-local, CGNAT, multicast or reserved ranges);
- follows redirects itself (max 5), re-checking each hop;
- after connecting, checks the peer address actually used, which closes most
  of the DNS-rebinding window between the check and the connect;
- streams the body and stops at ``max_bytes``, instead of buffering first.
"""

import asyncio
import ipaddress
import socket
from typing import List, Mapping, Tuple

import httpx

MAX_REDIRECTS = 5


class FetchError(Exception):
    """A user-facing reason the page couldn't be fetched."""


def is_public_address(ip: str) -> bool:
    """True if ``ip`` is a globally routable unicast address."""
    try:
        addr = ipaddress.ip_address(ip.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    return addr.is_global and not addr.is_multicast


async def resolve_host(host: str, port: int) -> List[str]:
    """All addresses ``host`` resolves to. Patched in tests."""
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


async def _check_url(url: httpx.URL) -> None:
    if url.scheme not in ("http", "https"):
        raise FetchError("Only http:// and https:// links can be imported.")
    host = url.host
    if not host:
        raise FetchError("That link has no host name.")
    try:
        ipaddress.ip_address(host)
        addresses = [host]
    except ValueError:
        try:
            addresses = await resolve_host(host, url.port or (443 if url.scheme == "https" else 80))
        except (socket.gaierror, UnicodeError) as e:
            raise FetchError(
                "Couldn't fetch that URL (unknown host). Check the link and try again."
            ) from e
    if not addresses or not all(is_public_address(a) for a in addresses):
        raise FetchError("That address can't be imported from.")


def _check_peer(response: httpx.Response) -> None:
    """Refuse if the connection actually went to a non-public address."""
    stream = response.extensions.get("network_stream")
    if stream is None:  # e.g. a mock transport in tests
        return
    peer = stream.get_extra_info("server_addr")
    if peer and not is_public_address(str(peer[0])):
        raise FetchError("That address can't be imported from.")


async def fetch_page(
    url: str,
    *,
    headers: Mapping[str, str],
    timeout: float,
    max_bytes: int,
) -> Tuple[str, str]:
    """Download ``url`` and return ``(final_url, text)``; raise ``FetchError`` otherwise."""
    try:
        current = httpx.URL(url)
    except (httpx.InvalidURL, TypeError) as e:
        raise FetchError("That doesn't look like a valid link.") from e

    too_large = FetchError(f"The page is too large to import (>{max_bytes // (1024 * 1024)} MB).")
    try:
        async with httpx.AsyncClient(
            timeout=timeout, follow_redirects=False, headers=dict(headers)
        ) as client:
            for _ in range(MAX_REDIRECTS + 1):
                await _check_url(current)
                async with client.stream("GET", current) as response:
                    _check_peer(response)
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise FetchError("The page redirected nowhere.")
                        current = current.join(location)
                        continue
                    if response.status_code >= 400:
                        raise FetchError(
                            f"The page at that URL returned HTTP {response.status_code}."
                        )
                    declared = response.headers.get("content-length", "")
                    if declared.isdigit() and int(declared) > max_bytes:
                        raise too_large
                    chunks: List[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            raise too_large
                        chunks.append(chunk)
                    body = b"".join(chunks)
                    encoding = response.charset_encoding or "utf-8"
                    try:
                        text = body.decode(encoding, errors="replace")
                    except LookupError:  # unknown charset label
                        text = body.decode("utf-8", errors="replace")
                    return str(current), text
            raise FetchError("The page redirected too many times.")
    except httpx.RequestError as e:
        raise FetchError(
            f"Couldn't fetch that URL ({type(e).__name__}). Check the link and try again."
        ) from e
