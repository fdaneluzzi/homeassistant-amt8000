"""Protocol-level tests for the AMT 8000 client, against a fake panel.

client.py has no Home Assistant imports, so it is loaded directly (importing
the `custom_components.amt8000` package would pull in Home Assistant).
"""
from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "amt8000_client",
    Path(__file__).resolve().parent.parent / "custom_components" / "amt8000" / "client.py",
)
client_mod = importlib.util.module_from_spec(_spec)
import sys  # noqa: E402

sys.modules["amt8000_client"] = client_mod  # dataclasses needs the module registered
_spec.loader.exec_module(client_mod)

Amt8000Client = client_mod.Amt8000Client
CannotConnect = client_mod.CannotConnect
InvalidAuth = client_mod.InvalidAuth


def frame(cmd: int, payload: bytes = b"") -> bytes:
    data = bytes([0x00, 0x00, 0x8F, 0xE0]) + (len(payload) + 2).to_bytes(2, "big")
    data += cmd.to_bytes(2, "big") + payload
    cs = 0
    for b in data:
        cs ^= b
    return data + bytes([(cs ^ 0xFF) & 0xFF])


def status_payload(
    *, armed: bool = False, open_zone: int | None = None, siren: bool = False, length: int = 143
) -> bytes:
    p = bytearray(length)
    p[0:4] = bytes([0x8B, 3, 2, 5])  # model, version 3.2.5
    p[12] = 0b00000011  # zones 1 and 2 enabled
    if open_zone is not None:
        p[38 + (open_zone - 1) // 8] |= 1 << ((open_zone - 1) % 8)
    p[20] = (0x60 if armed else 0x00) | (0x02 if siren else 0x00)
    p[21] = 0x80 | (0x01 if armed else 0x00)  # partition 0 (aggregate)
    p[22] = 0x80 | (0x01 if armed else 0x00)  # partition 1
    p[134] = 4  # battery full
    return bytes(p)


class FakePanel:
    """Minimal ISECNet v2 panel: replies per scripted auth results."""

    def __init__(self, auth_results: list[int] | None = None, status: bytes | None = None):
        self.auth_results = list(auth_results or [0x00])
        self.status = status if status is not None else status_payload()
        self.commands: list[int] = []
        self.sessions = 0
        self.active = 0
        self.max_active = 0
        self.server: asyncio.AbstractServer | None = None

    async def start(self) -> int:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        return self.server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        self.server.close()
        await self.server.wait_closed()

    async def _handle(self, reader, writer):
        self.sessions += 1
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            while True:
                header = await reader.readexactly(6)
                body = await reader.readexactly(int.from_bytes(header[4:6], "big") + 1)
                cmd = int.from_bytes(body[:2], "big")
                self.commands.append(cmd)
                if cmd == 0xF0F0:
                    result = self.auth_results.pop(0) if len(self.auth_results) > 1 else self.auth_results[0]
                    writer.write(frame(0xF0F0, bytes([result])))
                    if result != 0x00:
                        break
                elif cmd == 0x0B4A:
                    await asyncio.sleep(0.05)  # make overlap observable
                    writer.write(frame(0x0B4A, self.status))
                elif cmd == 0x0B50:
                    writer.write(frame(0x0B50, bytes(30)))
                elif cmd == 0x401E:
                    writer.write(frame(0x401E, b"\x00"))
                elif cmd == 0xF0F1:
                    break
                await writer.drain()
        except asyncio.IncompleteReadError:
            pass
        finally:
            self.active -= 1
            writer.close()


@pytest.fixture
async def panel_factory(monkeypatch):
    panels: list[FakePanel] = []

    async def no_sleep(_):
        return None

    monkeypatch.setattr(client_mod.asyncio, "sleep", no_sleep)

    async def make(**kw):
        panel = FakePanel(**kw)
        port = await panel.start()
        panels.append(panel)
        return panel, Amt8000Client("127.0.0.1", port, "123456", timeout=2.0)

    yield make
    for p in panels:
        await p.stop()


async def test_status_parsed(panel_factory):
    panel, client = await panel_factory(status=status_payload(armed=True, open_zone=2, siren=True))
    st = await client.get_status()
    assert st.version == "3.2.5"
    assert st.siren_live is True
    assert [z.number for z in st.zones] == [1, 2]
    assert [z.open for z in st.zones] == [False, True]
    assert st.battery == "full"
    assert [p.index for p in st.partitions] == [0, 1]
    assert client.last_status_payload == panel.status


async def test_invalid_password_not_retried(panel_factory):
    panel, client = await panel_factory(auth_results=[0x01])
    with pytest.raises(InvalidAuth):
        await client.get_status()
    assert panel.sessions == 1


async def test_transient_auth_rejection_is_retried(panel_factory):
    """Issue #1: a 0x9C auth rejection must be retried, then succeed."""
    panel, client = await panel_factory(auth_results=[0x9C, 0x9C, 0x00])
    st = await client.get_status()
    assert st.version == "3.2.5"
    assert panel.sessions == 3


async def test_persistent_auth_rejection_raises_after_3_attempts(panel_factory):
    panel, client = await panel_factory(auth_results=[0x9C])
    with pytest.raises(CannotConnect, match="0x9C"):
        await client.get_status()
    assert panel.sessions == 3


async def test_short_status_payload_is_reported_and_kept(panel_factory):
    """Issue #2: a truncated payload raises CannotConnect and is kept for diagnostics."""
    panel, client = await panel_factory(status=b"\x01")
    with pytest.raises(CannotConnect, match="Truncated"):
        await client.get_status()
    assert client.last_status_payload == b"\x01"


async def test_poll_and_command_never_overlap(panel_factory):
    """Issue #1: polling and arm/disarm share one lock — one session at a time."""
    panel, client = await panel_factory()
    await asyncio.gather(client.get_status(), client.disarm_partition(1), client.get_status())
    assert panel.max_active == 1
    assert 0x401E in panel.commands


async def test_session_released_after_failure(panel_factory):
    """Issue #2: failed auth must still close the session (no leaked connection)."""
    panel, client = await panel_factory(auth_results=[0x9C])
    with pytest.raises(CannotConnect):
        await client.get_status()
    assert panel.active == 0
