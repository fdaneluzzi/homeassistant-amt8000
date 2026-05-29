"""Async ISECNet v2 client for Intelbras AMT 8000.

Protocol reference: github.com/caarlos0/homekit-amt8000 (Go reference implementation)
Confirmed against AMT 8000 firmware 3.2.5 via live packet captures.
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging

_LOGGER = logging.getLogger(__name__)

_DST = [0x00, 0x00]
_SRC = [0x8F, 0xE0]

_CMD_AUTH       = [0xF0, 0xF0]
_CMD_STATUS     = [0x0B, 0x4A]
_CMD_ARM        = [0x40, 0x1E]
_CMD_DISCONNECT = [0xF0, 0xF1]

_SUBCMD_DISARM = 0x00
_SUBCMD_ARM    = 0x01

ALL_PARTITIONS = 0xFF

_STATES = {0: "DISARMED", 1: "PARTIAL", 3: "ARMED"}
_BATTERY = {1: "dead", 2: "low", 3: "middle", 4: "full"}


class CannotConnect(Exception):
    """Raised when the connection to the panel fails."""


class InvalidAuth(Exception):
    """Raised when the panel rejects the password."""


class OpenZones(Exception):
    """Raised when arm is blocked because zones are open."""


@dataclasses.dataclass
class Zone:
    number: int
    enabled: bool
    open: bool
    violated: bool
    bypassed: bool
    tamper: bool
    low_battery: bool

    @property
    def is_open(self) -> bool:
        return self.open or self.violated


@dataclasses.dataclass
class Partition:
    index: int
    enabled: bool
    armed: bool
    stay: bool
    firing: bool
    fired: bool


@dataclasses.dataclass
class PanelStatus:
    model: int
    version: str
    state: str
    siren_live: bool
    zones_firing: bool
    zones_closed: bool
    battery: str
    tamper: bool
    partitions: list[Partition]
    zones: list[Zone]


class Amt8000Client:
    def __init__(self, host: str, port: int, password: str, timeout: float = 5.0) -> None:
        self._host = host
        self._port = port
        self._password = password
        self._timeout = timeout

    # ── wire helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _checksum(data: list[int]) -> int:
        cs = 0
        for b in data:
            cs ^= b
        return (cs ^ 0xFF) & 0xFF

    @staticmethod
    def _encode_password(pwd: str) -> list[int]:
        """Contact-ID BCD encoding: 0 digit → 0x0A; 4-digit passwords left-padded."""
        digits = [(int(c) % 10 or 0x0A) for c in pwd]
        if len(pwd) == 4:
            digits = [0x0A, 0x0A] + digits
        return digits  # always 6 bytes

    def _packet(self, cmd: list[int], payload: list[int] | None = None) -> bytes:
        payload = payload or []
        length = len(payload) + 2  # 2 cmd bytes count in length field
        data = _DST + _SRC + [0x00, length] + cmd + payload
        data.append(self._checksum(data))
        return bytes(data)

    async def _read_frame(self, reader: asyncio.StreamReader) -> bytes:
        """Read one complete ISECNet v2 frame from the stream."""
        try:
            header = await asyncio.wait_for(reader.readexactly(6), self._timeout)
            length = int.from_bytes(header[4:6], "big")
            body = await asyncio.wait_for(reader.readexactly(length + 1), self._timeout)
        except (asyncio.IncompleteReadError, asyncio.TimeoutError) as exc:
            raise CannotConnect("Incomplete response from panel") from exc
        return header + body

    async def _connect_and_auth(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port), self._timeout
            )
        except (OSError, asyncio.TimeoutError) as exc:
            raise CannotConnect(f"Cannot connect to {self._host}:{self._port}") from exc

        auth_payload = [0x00] + self._encode_password(self._password) + [0x10]
        writer.write(self._packet(_CMD_AUTH, auth_payload))
        await writer.drain()

        resp = await self._read_frame(reader)
        result = resp[8] if len(resp) > 8 else -1
        if result == 0x01:
            writer.close()
            raise InvalidAuth("Invalid password")
        if result != 0x00:
            writer.close()
            raise CannotConnect(f"Auth rejected: code=0x{result:02X}")

        return reader, writer

    async def _disconnect(self, writer: asyncio.StreamWriter) -> None:
        try:
            writer.write(self._packet(_CMD_DISCONNECT))
            await asyncio.wait_for(writer.drain(), 1.0)
        except Exception:
            pass
        try:
            writer.close()
            await asyncio.wait_for(writer.wait_closed(), 1.0)
        except Exception:
            pass

    # ── public API ────────────────────────────────────────────────────────────

    async def get_status(self) -> PanelStatus:
        reader, writer = await self._connect_and_auth()
        try:
            writer.write(self._packet(_CMD_STATUS))
            await writer.drain()
            resp = await self._read_frame(reader)
        except Exception:
            await self._disconnect(writer)
            raise
        await self._disconnect(writer)

        # payload = full_frame[8 : 8+payload_length]
        length = int.from_bytes(resp[4:6], "big") - 2  # subtract 2 cmd bytes
        payload = resp[8 : 8 + length]
        return self._parse_status(payload)

    async def arm_partition(self, partition_idx: int) -> None:
        await self._arm_cmd(partition_idx, _SUBCMD_ARM)

    async def disarm_partition(self, partition_idx: int) -> None:
        await self._arm_cmd(partition_idx, _SUBCMD_DISARM)

    async def _arm_cmd(self, partition_idx: int, subcmd: int) -> None:
        reader, writer = await self._connect_and_auth()
        try:
            writer.write(self._packet(_CMD_ARM, [partition_idx, subcmd]))
            await writer.drain()
            if subcmd == _SUBCMD_ARM:
                try:
                    resp = await self._read_frame(reader)
                    body_start = 8
                    if len(resp) > body_start and resp[body_start] == 0xF0:
                        raise OpenZones("Cannot arm: zones are open")
                except CannotConnect:
                    pass  # panel may close before responding; assume success
        finally:
            await self._disconnect(writer)

    # ── status parser ─────────────────────────────────────────────────────────

    @staticmethod
    def _parse_status(payload: bytes) -> PanelStatus:
        if len(payload) < 143:
            raise CannotConnect(f"Truncated status payload: {len(payload)} bytes (expected 143)")

        status_byte = payload[20]

        partitions: list[Partition] = []
        for i in range(16):
            b = payload[21 + i]
            if b & 0x80:
                partitions.append(Partition(
                    index=i,
                    enabled=True,
                    armed=bool(b & 0x01),
                    stay=bool(b & 0x40),
                    firing=bool(b & 0x04),
                    fired=bool(b & 0x08),
                ))

        zones: list[Zone] = []
        for i in range(56):
            bi, bit = divmod(i, 8)
            if not (payload[12 + bi] & (1 << bit)):
                continue
            zones.append(Zone(
                number=i + 1,
                enabled=True,
                open=bool(payload[38 + bi] & (1 << bit)),
                violated=bool(payload[46 + bi] & (1 << bit)),
                bypassed=bool(payload[54 + bi] & (1 << bit)) if bi < 8 else False,
                tamper=bool(payload[89 + bi] & (1 << bit)) if 89 + bi < 143 else False,
                low_battery=bool(payload[105 + bi] & (1 << bit)) if 105 + bi < 143 else False,
            ))

        return PanelStatus(
            model=payload[0],
            version=f"{payload[1]}.{payload[2]}.{payload[3]}",
            state=_STATES.get((status_byte >> 5) & 0x03, "UNKNOWN"),
            siren_live=bool(status_byte & 0x02),
            zones_firing=bool(status_byte & 0x08),
            zones_closed=bool(status_byte & 0x04),
            battery=_BATTERY.get(payload[134], "unknown"),
            tamper=bool(payload[71] & 0x02),
            partitions=partitions,
            zones=zones,
        )
