"""Sends batched metrics to Icelake via Prometheus remote write protocol."""

import asyncio
import base64
import logging

import aiohttp
import snappy

from .protobuf import encode_write_request

_LOGGER = logging.getLogger(__name__)


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

    async def start(self) -> None:
        self._session = aiohttp.ClientSession()
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

    async def _send_loop(self) -> None:
        while True:
            await asyncio.sleep(self._send_interval)
            await self._flush()

    async def _flush(self) -> None:
        async with self._lock:
            if not self._buffer:
                return
            batch = self._buffer
            self._buffer = []

        protobuf_data = encode_write_request(batch)
        compressed = snappy.compress(protobuf_data)

        url = f"{self._endpoint}?prometheus_server={self._source_id}"
        headers = {
            "Content-Type": "application/x-protobuf",
            "Content-Encoding": "snappy",
            "Authorization": self._auth_header,
        }

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
                elif resp.status == 401:
                    body = await resp.text()
                    _LOGGER.error("Icelake auth failed: %s", body)
                else:
                    body = await resp.text()
                    _LOGGER.error(
                        "Icelake rejected write (HTTP %d): %s", resp.status, body
                    )
        except aiohttp.ClientError as err:
            _LOGGER.error("Failed to send metrics to Icelake: %s", err)
            async with self._lock:
                self._buffer = batch + self._buffer

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
