# AMT 8000 Protocol Documentation

## Overview

The Intelbras AMT 8000 communicates over **ISECNet v2** — a proprietary binary protocol over TCP on port 9009. This is distinct from the `0xe7` protocol used by lower-end AMT panels (1016 NET, 2018 NET).

## Frame format

```
[dst_high] [dst_low] [src_high] [src_low] [len_high] [len_low] [cmd_high] [cmd_low] [payload...] [xor_checksum]
```

- `dst` / `src`: 16-bit client/server IDs. Client uses `0x8FE0`, panel uses `0x0000`.
- `len`: number of bytes that follow the length field, **excluding** the checksum. Includes the 2 cmd bytes.
- `checksum`: XOR of all preceding bytes, then XOR with `0xFF`.

## Commands

| Command | Hex | Direction | Description |
|---------|-----|-----------|-------------|
| Auth | `0xF0F0` | → panel | Authenticate. Payload: `[device_type, p1..p6, sw_version]` |
| Status | `0x0B4A` | → panel | Request 143-byte status payload |
| Arm/Disarm | `0x401E` | → panel | Payload: `[partition_idx, 0x01=arm / 0x00=disarm]` |
| Disconnect | `0xF0F1` | → panel | Clean session close |

## Password encoding (Contact-ID BCD)

Digits are encoded one byte per digit with `0` → `0x0A`. 4-digit passwords are left-padded with two `0x0A` bytes to reach 6 bytes total.

```python
digits = [(int(c) % 10 or 0x0A) for c in password]
if len(password) == 4:
    digits = [0x0A, 0x0A] + digits
```

## Status payload (143 bytes)

| Byte(s) | Field |
|---------|-------|
| 0 | Model code (`0x8B` on firmware 3.2.5) |
| 1–3 | Firmware version (major.minor.patch) |
| 12–18 | Zone enabled bitmask (56 zones, bit j of byte i = zone i×8+j+1) |
| 20 | Global status: bits `[7:6]`=unused `[6:5]`=arm state `[3]`=zones firing `[2]`=zones closed `[1]`=siren live |
| 21–36 | Partition status bytes (16 partitions). Bit `7`=enabled `6`=stay `3`=fired `2`=firing `0`=armed |
| 38–44 | Zone open bitmask |
| 46–52 | Zone violated bitmask |
| 54–61 | Zone bypassed bitmask |
| 71 | Panel tamper (bit 1) |
| 89–95 | Zone tamper bitmask |
| 105–111 | Zone low-battery bitmask |
| 134 | Battery: `1`=dead `2`=low `3`=middle `4`=full |

### Arm state (bits 6:5 of byte 20)

| Value | State |
|-------|-------|
| `0` | Disarmed |
| `1` | Partial (some groups armed) |
| `3` | Armed away (all groups armed) |

## Partition index 0 — AND aggregate

Protocol partition index 0 is not a user-configurable group. Its `armed` bit mirrors `AND(all other enabled partitions)`: it is armed only when every real group is armed. Confirmed via live observation across all arm/disarm combinations. User groups start at index 1.

## References

- `caarlos0/homekit-amt8000` — Go implementation, most complete status parser
- `merencia/amt8000-hass-integration` — Python HA integration (ISECNet v2 client)
- `elvis-epx/alarme-intelbras` — IP receptor for push-mode events
