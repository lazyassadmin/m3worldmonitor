"""Shared async HTTP client with retry + concurrency limits.

Every ingestion source should use ``get_client()`` + ``fetch()`` — never
construct a raw ``httpx.AsyncClient``. This guarantees consistent retry,
timeout, rate-limit, and User-Agent behavior.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from loguru import logger
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

USER_AGENT = "PoliWatch/0.1 (+https://github.com/your-org/poliwatch)"
DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)
DEFAULT_LIMITS = httpx.Limits(max_connections=5, max_keepalive_connections=5)

# Global concurrency cap across the process (Congress.gov rate-limit guard).
_SEMAPHORE = asyncio.Semaphore(5)
_CLIENT: httpx.AsyncClient | None = None
_CLIENT_LOCK = asyncio.Lock()


async def get_client() -> httpx.AsyncClient:
    """Return a process-wide shared AsyncClient."""
    global _CLIENT
    if _CLIENT is None or _CLIENT.is_closed:
        async with _CLIENT_LOCK:
            if _CLIENT is None or _CLIENT.is_closed:
                _CLIENT = httpx.AsyncClient(
                    timeout=DEFAULT_TIMEOUT,
                    limits=DEFAULT_LIMITS,
                    headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                    follow_redirects=True,
                )
    return _CLIENT


async def close_client() -> None:
    global _CLIENT
    if _CLIENT is not None and not _CLIENT.is_closed:
        await _CLIENT.aclose()
        _CLIENT = None


class RetryableHTTPError(Exception):
    """Signals that a 429/5xx response should be retried."""


def _should_retry(response: httpx.Response) -> bool:
    return response.status_code == 429 or 500 <= response.status_code < 600


async def fetch(
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    json: Any = None,
    accept: str = "application/json",
    max_attempts: int = 5,
) -> httpx.Response:
    """Issue an HTTP request with retries, concurrency cap, and logging.

    Retries on transport errors and 429/5xx with exponential backoff + jitter.
    Raises the final response's exception if all attempts fail.
    """
    client = await get_client()
    merged_headers = {"Accept": accept}
    if headers:
        merged_headers.update(headers)

    async for attempt in AsyncRetrying(
        reraise=True,
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential_jitter(initial=1.0, max=30.0),
        retry=retry_if_exception_type((httpx.TransportError, RetryableHTTPError)),
    ):
        with attempt:
            async with _SEMAPHORE:
                logger.debug("{} {} params={}", method, url, params)
                response = await client.request(
                    method, url, params=params, headers=merged_headers, json=json
                )
            if _should_retry(response):
                snippet = response.text[:200].replace("\n", " ") if response.text else ""
                logger.warning(
                    "{} {} → {} (retryable): {}",
                    method,
                    url,
                    response.status_code,
                    snippet,
                )
                raise RetryableHTTPError(f"{response.status_code} {url}")
            return response
    raise RuntimeError("unreachable: AsyncRetrying exited without returning")  # pragma: no cover


async def fetch_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    """GET URL and return parsed JSON."""
    response = await fetch("GET", url, params=params, headers=headers)
    response.raise_for_status()
    return response.json()


async def fetch_bytes(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> bytes:
    """GET URL and return raw bytes."""
    response = await fetch("GET", url, params=params, headers=headers, accept="*/*")
    response.raise_for_status()
    return response.content
