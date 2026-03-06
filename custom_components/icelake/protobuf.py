"""Minimal Prometheus remote write protobuf encoder.

Encodes WriteRequest without requiring the protobuf library.
Wire format reference: https://protobuf.dev/programming-guides/encoding/
"""

import struct


def _encode_varint(value: int) -> bytes:
    result = bytearray()
    while value > 0x7F:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    result.append(value & 0x7F)
    return bytes(result)


def _encode_signed_varint(value: int) -> bytes:
    if value < 0:
        value += 1 << 64
    return _encode_varint(value)


def _encode_field_varint(field_number: int, value: int) -> bytes:
    tag = _encode_varint((field_number << 3) | 0)
    return tag + _encode_signed_varint(value)


def _encode_field_double(field_number: int, value: float) -> bytes:
    tag = _encode_varint((field_number << 3) | 1)
    return tag + struct.pack("<d", value)


def _encode_field_bytes(field_number: int, data: bytes) -> bytes:
    tag = _encode_varint((field_number << 3) | 2)
    return tag + _encode_varint(len(data)) + data


def _encode_field_string(field_number: int, value: str) -> bytes:
    return _encode_field_bytes(field_number, value.encode("utf-8"))


def encode_label(name: str, value: str) -> bytes:
    return _encode_field_string(1, name) + _encode_field_string(2, value)


def encode_sample(value: float, timestamp_ms: int) -> bytes:
    return _encode_field_double(1, value) + _encode_field_varint(2, timestamp_ms)


def encode_timeseries(
    labels: list[tuple[str, str]], value: float, timestamp_ms: int
) -> bytes:
    data = b""
    for name, val in labels:
        data += _encode_field_bytes(1, encode_label(name, val))
    data += _encode_field_bytes(2, encode_sample(value, timestamp_ms))
    return data


def encode_write_request(
    timeseries_list: list[tuple[list[tuple[str, str]], float, int]],
) -> bytes:
    """Encode a list of (labels, value, timestamp_ms) tuples into a WriteRequest protobuf."""
    data = b""
    for labels, value, timestamp_ms in timeseries_list:
        ts_bytes = encode_timeseries(labels, value, timestamp_ms)
        data += _encode_field_bytes(1, ts_bytes)
    return data
