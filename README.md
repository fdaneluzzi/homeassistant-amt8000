# Intelbras AMT 8000 — Home Assistant Integration

[![HACS Custom][hacs-shield]][hacs-url]
[![GitHub Release][release-shield]][release-url]

Native Home Assistant integration for the **Intelbras AMT 8000** alarm panel, communicating directly over the local network via the ISECNet v2 protocol. No cloud dependency at runtime.

## Features

- **Arm / Disarm per group** — individual control of each configured partition
- **Zone monitoring** — binary sensor per zone (open / closed / violated)
- **Live siren detection** — binary sensor + event entity for automations
- **Device triggers** — "Alarm triggered" trigger in the automation UI (no YAML needed)
- **Local only** — direct TCP connection to the panel on port 9009

## Tested hardware

| Model | Firmware | Status |
|-------|----------|--------|
| AMT 8000 (model byte `0x8B`) | 3.2.5 | ✅ Working |

## Installation via HACS

1. Open HACS → Integrations → ⋮ → **Custom repositories**
2. Add `https://github.com/fdaneluzzi/homeassistant-amt8000` — Category: **Integration**
3. Install **Intelbras AMT 8000** and restart Home Assistant
4. Go to **Settings → Devices & Services → Add Integration** → search **Intelbras AMT 8000**
5. Enter your panel's IP, port (default `9009`), and password

## Entities created

| Entity | Type | Description |
|--------|------|-------------|
| `alarm_control_panel.amt8000_group_N` | Alarm panel | One per configured group. Arm Away / Disarm. |
| `binary_sensor.amt8000_zone_N` | Binary sensor | Open / closed. Extra attrs: violated, bypassed, tamper, low_battery. |
| `binary_sensor.amt8000_siren` | Binary sensor (sound) | True while siren is actively sounding. |
| `event.amt8000_alarm` | Event | Fires `alarm_triggered` on siren rising edge. |

## Protocol notes

The AMT 8000 uses **ISECNet v2** (TCP 9009), which is distinct from the `0xe7` protocol used by lower-end AMT models (1016/2018 NET).

Partition index 0 in the protocol is a read-only AND-aggregate (armed only when all groups are armed) and is intentionally excluded from HA entities. User groups start at protocol index 1.

Full protocol documentation in [`docs/PROTOCOL.md`](docs/PROTOCOL.md).

## License

MIT

[hacs-shield]: https://img.shields.io/badge/HACS-Custom-orange.svg
[hacs-url]: https://hacs.xyz
[release-shield]: https://img.shields.io/github/release/fdaneluzzi/homeassistant-amt8000.svg
[release-url]: https://github.com/fdaneluzzi/homeassistant-amt8000/releases
