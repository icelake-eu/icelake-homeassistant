"""Sends batched metrics to Icelake via Prometheus remote write protocol."""

import asyncio
import base64
import logging
import random

import aiohttp
import snappy

from .const import (
    MAX_BUFFER_SAMPLES,
    MAX_SAMPLES_PER_REQUEST,
    REQUEST_TIMEOUT,
    RETRY_BASE_DELAY,
    RETRY_MAX_DELAY,
)
from .protobuf import encode_write_request

_LOGGER = logging.getLogger(__name__)

# Statuses that indicate a temporary problem on the Icelake side
RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}


class IcelakeSender:
    """Batches and sends Prometheus remote write requests to Icelake."""

    def __init__(
        self,
        endpoint: str,
        client_id: str,
        api_key: str,
        source_id: str,
        send_interval: int,
    ) -> None:
        self._endpoint = endpoint.rstrip("/") + "/prometheus/v1/write"
        self._source_id = source_id
        self._send_interval = send_interval
        self._auth_header = "Basic " + base64.b64encode(
            f"{client_id}:{api_key}".encode()
        ).decode()
        self._buffer: list[tuple[list[tuple[str, str]], float, int]] = []
        self._lock = asyncio.Lock()
        self._session: aiohttp.ClientSession | None = None
        self._task: asyncio.Task | None = None
        self._failures = 0
        self._retry_after: float | None = None
        self._dropped = 0

    async def start(self) -> None:
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        )
        self._task = asyncio.create_task(self._send_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._flush()
        if self._session:
            await self._session.close()

    def add_sample(
        self, labels: list[tuple[str, str]], value: float, timestamp_ms: int
    ) -> None:
        self._buffer.append((labels, value, timestamp_ms))
        self._trim_buffer()

    async def _send_loop(self) -> None:
        while True:
            await asyncio.sleep(self._next_delay())
            await self._flush()

    def _next_delay(self) -> float:
        """Return the send interval, or a backoff delay while sends are failing."""
        if self._failures == 0:
            return self._send_interval
        delay = min(RETRY_BASE_DELAY * 2 ** (self._failures - 1), RETRY_MAX_DELAY)
        # Jitter so many instances don't hammer Icelake in lockstep on recovery
        delay = delay / 2 + random.uniform(0, delay / 2)
        if self._retry_after is not None:
            delay = max(delay, min(self._retry_after, RETRY_MAX_DELAY))
        return delay

    def _trim_buffer(self) -> None:
        overflow = len(self._buffer) - MAX_BUFFER_SAMPLES
        if overflow > 0:
            del self._buffer[:overflow]
            if self._dropped == 0:
                _LOGGER.warning(
                    "Icelake buffer full (%d samples), dropping oldest samples",
                    MAX_BUFFER_SAMPLES,
                )
            self._dropped += overflow

    async def _flush(self) -> None:
        async with self._lock:
            if not self._buffer:
                return
            batch = self._buffer
            self._buffer = []

        try:
            while batch:
                chunk = batch[:MAX_SAMPLES_PER_REQUEST]
                if not await self._send(chunk):
                    break
                batch = batch[MAX_SAMPLES_PER_REQUEST:]
        finally:
            # Keep unsent samples (retryable failure or cancellation) for the next attempt
            if batch:
                async with self._lock:
                    self._buffer = batch + self._buffer
                    self._trim_buffer()

        if batch:
            self._failures += 1
            _LOGGER.debug(
                "Retrying in backoff, %d consecutive failures", self._failures
            )
        elif self._failures:
            _LOGGER.info(
                "Icelake reachable again after %d failed attempts", self._failures
            )
            self._failures = 0
            self._retry_after = None
        if not batch and self._dropped:
            _LOGGER.warning(
                "Dropped %d samples in total while Icelake was unavailable",
                self._dropped,
            )
            self._dropped = 0

    async def _send(self, batch) -> bool:
        """Send one request. Return False if it failed and should be retried."""
        protobuf_data = encode_write_request(batch)
        compressed = snappy.compress(protobuf_data)

        url = f"{self._endpoint}?prometheus_server={self._source_id}"
        headers = {
            "Content-Type": "application/x-protobuf",
            "Content-Encoding": "snappy",
            "Authorization": self._auth_header,
        }

        self._retry_after = None
        try:
            async with self._session.post(
                url, data=compressed, headers=headers
            ) as resp:
                if resp.status == 200:
                    _LOGGER.debug(
                        "Sent %d samples to Icelake (%d bytes compressed)",
                        len(batch),
                        len(compressed),
                    )
                    return True
                body = await resp.text()
                if resp.status in RETRYABLE_STATUSES:
                    self._retry_after = _parse_retry_after(
                        resp.headers.get("Retry-After")
                    )
                    self._log_retryable(f"HTTP {resp.status}: {body}")
                    return False
                if resp.status == 401:
                    _LOGGER.error("Icelake auth failed: %s", body)
                else:
                    _LOGGER.error(
                        "Icelake rejected write (HTTP %d): %s", resp.status, body
                    )
                # Permanent rejection, retrying the same data won't help
                return True
        except (aiohttp.ClientError, TimeoutError) as err:
            self._log_retryable(str(err) or type(err).__name__)
            return False

    def _log_retryable(self, reason: str) -> None:
        # Warn once per outage, then keep quiet until it recovers
        if self._failures == 0:
            _LOGGER.warning(
                "Icelake temporarily unavailable (%s), will retry with backoff",
                reason,
            )
        else:
            _LOGGER.debug("Icelake still unavailable: %s", reason)

    async def test_connection(self) -> tuple[bool, str]:
        """Test connectivity and auth by sending an empty write request."""
        protobuf_data = encode_write_request([])
        compressed = snappy.compress(protobuf_data)

        url = f"{self._endpoint}?prometheus_server={self._source_id}"
        headers = {
            "Content-Type": "application/x-protobuf",
            "Content-Encoding": "snappy",
            "Authorization": self._auth_header,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, data=compressed, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        return True, "ok"
                    if resp.status == 401:
                        return False, "invalid_auth"
                    return False, "cannot_connect"
        except aiohttp.ClientError:
            return False, "cannot_connect"


def _parse_retry_after(value: str | None) -> float | None:
    """Parse a Retry-After header given in seconds; HTTP-date form is ignored."""
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None
