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
_CMD_DEVICES    = [0x0B, 0x50]
_CMD_ARM        = [0x40, 0x1E]
_CMD_BYPASS     = [0x40, 0x1F]
_CMD_PGM        = [0x45, 0xAF]
_CMD_DISCONNECT = [0xF0, 0xF1]

_SUBCMD_DISARM = 0x00
_SUBCMD_ARM    = 0x01

_NACK = 0xF0FD

ALL_PARTITIONS = 0xFF
MAX_PGMS = 16
# PGM on/off bits live in the 0x0B4A status payload; which indexes exist
# (are actually recorded on the panel) comes from the 0x0B50 response.
_PGM_ON_OFFSET = 137
_PGM_COMM_FAIL_OFFSET = 87
_PGM_TAMPER_OFFSET = 103
_PGM_LOW_BATTERY_OFFSET = 119

_STATES = {0: "DISARMED", 1: "PARTIAL", 3: "ARMED"}
_BATTERY = {1: "dead", 2: "low", 3: "middle", 4: "full"}


class CannotConnect(Exception):
    """Raised when the connection to the panel fails."""


class InvalidAuth(Exception):
    """Raised when the panel rejects the password."""


class OpenZones(Exception):
    """Raised when arm is blocked because zones are open."""


class BypassError(Exception):
    """Raised when the panel rejects a zone bypass command."""


class PgmError(Exception):
    """Raised when the panel rejects a PGM command."""


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
        return self.open


@dataclasses.dataclass
class Partition:
    index: int
    enabled: bool
    armed: bool
    stay: bool
    firing: bool
    fired: bool


@dataclasses.dataclass
class Pgm:
    index: int
    on: bool
    tamper: bool
    low_battery: bool
    comm_fail: bool


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
    pgms: list[Pgm]


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
            status_resp = await self._read_frame(reader)

            # PGM discovery (0x0B50) is best-effort and EXPERIMENTAL: some
            # firmwares may not support it or may not reply at all. Never let
            # it break status polling, which is the core, verified feature.
            pgm_indexes: list[int] = []
            try:
                writer.write(self._packet(_CMD_DEVICES))
                await writer.drain()
                devices_resp = await self._read_frame(reader)
                pgm_indexes = self._recorded_pgm_indexes(
                    self._response_payload(devices_resp, expected=_CMD_DEVICES)
                )
            except CannotConnect as exc:
                _LOGGER.debug("PGM discovery (0x0B50) failed, skipping: %s", exc)
        except Exception:
            await self._disconnect(writer)
            raise
        await self._disconnect(writer)

        # No command-match check here: preserve the original, hardware-verified
        # behavior of trusting the frame's own length field for the status reply.
        payload = self._response_payload(status_resp)
        return self._parse_status(payload, pgm_indexes)

    async def arm_partition(self, partition_idx: int) -> None:
        await self._arm_cmd(partition_idx, _SUBCMD_ARM)

    async def disarm_partition(self, partition_idx: int) -> None:
        await self._arm_cmd(partition_idx, _SUBCMD_DISARM)

    async def bypass_zone(self, zone_index: int, enabled: bool) -> None:
        """Bypass (anular) or restore a single zone by its 0-based index.

        EXPERIMENTAL: not verified against a real AMT 8000 panel by the
        maintainer. If the panel rejects or misbehaves on this command,
        please open an issue with the debug log.
        """
        if not 0 <= zone_index < 56:
            raise BypassError(f"Invalid zone index: {zone_index}")

        reader, writer = await self._connect_and_auth()
        try:
            writer.write(self._packet(_CMD_BYPASS, [zone_index, 0x01 if enabled else 0x00]))
            await writer.drain()
            resp = await self._read_frame(reader)
            self._raise_for_nack(resp, BypassError, "Zone bypass")
        finally:
            await self._disconnect(writer)

    async def set_pgm(self, pgm_index: int, enabled: bool) -> None:
        """Turn a PGM (auxiliary output) on or off by its 0-based index.

        EXPERIMENTAL: not verified against a real AMT 8000 panel by the
        maintainer. If the panel rejects or misbehaves on this command,
        please open an issue with the debug log.
        """
        if not 0 <= pgm_index < MAX_PGMS:
            raise PgmError(f"Invalid PGM index: {pgm_index}")

        reader, writer = await self._connect_and_auth()
        try:
            writer.write(self._packet(_CMD_PGM, [pgm_index, 0x01 if enabled else 0x00]))
            await writer.drain()
            resp = await self._read_frame(reader)
            self._raise_for_nack(resp, PgmError, "PGM command")
        finally:
            await self._disconnect(writer)

    @staticmethod
    def _raise_for_nack(resp: bytes, exc_cls: type[Exception], what: str) -> None:
        if len(resp) < 8:
            raise exc_cls(f"{what}: invalid response from panel")
        command = int.from_bytes(resp[6:8], "big")
        if command == _NACK:
            error_code = resp[8] if len(resp) > 8 else -1
            _LOGGER.warning("%s rejected by panel: NACK code 0x%02X", what, error_code)
            raise exc_cls(f"{what} rejected by panel (code 0x{error_code:02X})")

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
    def _response_payload(frame: bytes, expected: list[int] | None = None) -> bytes:
        """Extract a response's payload; empty on NACK, short frame, or command mismatch."""
        if len(frame) < 8:
            return b""
        command = int.from_bytes(frame[6:8], "big")
        if command == _NACK:
            return b""
        if expected is not None and command != int.from_bytes(bytes(expected), "big"):
            return b""
        length = int.from_bytes(frame[4:6], "big") - 2  # subtract 2 cmd bytes
        if length < 0:
            return b""
        return frame[8 : 8 + length]

    @staticmethod
    def _recorded_pgm_indexes(devices_payload: bytes) -> list[int]:
        """0-based PGM indexes marked as recorded in the 0x0B50 response.

        EXPERIMENTAL: byte layout not verified against a real panel.
        """
        if len(devices_payload) < 26:
            return []
        indexes: list[int] = []
        for bit in range(4):
            if devices_payload[25] & (1 << (4 + bit)):
                indexes.append(bit)
        if len(devices_payload) >= 27:
            for bit in range(8):
                if devices_payload[26] & (1 << bit):
                    indexes.append(bit + 4)
        if len(devices_payload) >= 28:
            for bit in range(4):
                if devices_payload[27] & (1 << bit):
                    indexes.append(bit + 12)
        return indexes

    @staticmethod
    def _mask_bit(payload: bytes, offset: int, index: int) -> bool:
        byte_index, bit_index = divmod(index, 8)
        pos = offset + byte_index
        return bool(payload[pos] & (1 << bit_index)) if pos < len(payload) else False

    @classmethod
    def _parse_pgms(cls, payload: bytes, indexes: list[int]) -> list[Pgm]:
        return [
            Pgm(
                index=i,
                on=cls._mask_bit(payload, _PGM_ON_OFFSET, i),
                tamper=cls._mask_bit(payload, _PGM_TAMPER_OFFSET, i),
                low_battery=cls._mask_bit(payload, _PGM_LOW_BATTERY_OFFSET, i),
                comm_fail=cls._mask_bit(payload, _PGM_COMM_FAIL_OFFSET, i),
            )
            for i in indexes
            if 0 <= i < MAX_PGMS
        ]

    @classmethod
    def _parse_status(cls, payload: bytes, pgm_indexes: list[int] | None = None) -> PanelStatus:
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
            pgms=cls._parse_pgms(payload, pgm_indexes or []),
        )
