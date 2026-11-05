# Intelbras AMT 8000 — Home Assistant Integration

[![HACS Custom][hacs-shield]][hacs-url]
[![GitHub Release][release-shield]][release-url]
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-fdaneluzzi-FFDD00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/fdaneluzzi)

Native Home Assistant integration for the **Intelbras AMT 8000** alarm panel, communicating directly over the local network via the ISECNet v2 protocol. No cloud dependency at runtime.

## Features

- **Arm / Disarm per group** — individual control of each configured partition
- **Zone monitoring** — binary sensor per zone (open / closed / violated)
- **Live siren detection** — binary sensor + event entity for automations
- **Device triggers** — "Alarm triggered" trigger in the automation UI (no YAML needed)
- **Read-only mode** — option to monitor only: no arm/disarm, PGM or bypass entities are created
- **Diagnostic entities** — panel battery level and tamper
- **Re-authentication** — if the panel rejects the password, Home Assistant asks for the new one instead of retrying forever
- **Diagnostics download** — redacted raw status payload, for reporting issues on untested firmware
- **Local only** — direct TCP connection to the panel on port 9009

## Tested hardware

| Model | Firmware | Status |
|-------|----------|--------|
| AMT 8000 (model byte `0x8B`) | 3.2.5 | ✅ Working |
| AMT 8000 PRO | 3.2.72 | ❓ Unconfirmed — see [#2](https://github.com/fdaneluzzi/homeassistant-amt8000/issues/2) |

Running a different model or firmware? Add the integration, then download **Settings → Devices & Services → Intelbras AMT 8000 → ⋮ → Download diagnostics** and attach it to an issue — it contains the panel's raw reply, with the IP and password redacted.

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
| `binary_sensor.amt8000_tamper` | Binary sensor (diagnostic) | Panel tamper flag. |
| `sensor.amt8000_battery` | Sensor (diagnostic) | Backup battery level: `dead` / `low` / `middle` / `full`. |

## Monitoring only (read-only mode)

**Settings → Devices & Services → Intelbras AMT 8000 → Configure → Read-only.** The integration then creates only sensors and the alarm event; it never sends arm/disarm, PGM or bypass commands. Use the `amt8000_alarm_triggered` event (or the *Alarm triggered* device trigger) in automations.

## Troubleshooting

- The panel accepts only a few simultaneous sessions. Close *AMT Remoto* (desktop/mobile) while testing.
- Enable debug logs and attach the lines starting with `Auth response`, `Frame received` and `Short status payload` to an issue:

```yaml
logger:
  logs:
    custom_components.amt8000: debug
```

## ⚠️ Experimental: PGM outputs and zone bypass

Two additional `switch` entities are shipped disabled by default (enable them per-entity in **Settings → Devices & Services → Entities** if you want them):

- `switch.amt8000_pgm_N` — turns a PGM (auxiliary output) on the panel on/off. Only created for PGMs the panel reports as recorded.
- `switch.amt8000_zone_N_bypass` — anula (bypass) or reativa an individual zone, so it can be armed while open/violated.

**These rely on protocol commands (`0x0B50`, `0x40 1F`, `0x45 AF`) that have not been verified against a real AMT 8000 panel by the maintainer** — unlike the rest of this integration (see [Tested hardware](#tested-hardware)). The byte layout was derived from a community fork, not from a live capture against this maintainer's hardware. That's why the entities are opt-in and disabled by default.

If you enable them and something doesn't work as expected, please [open an issue](https://github.com/fdaneluzzi/homeassistant-amt8000/issues) with:
- Your panel model/firmware
- The debug log for the failing call (Settings → Logs, filter by `custom_components.amt8000` — command rejections are logged as `WARNING` with the panel's NACK code)

## Protocol notes

The AMT 8000 uses **ISECNet v2** (TCP 9009), which is distinct from the `0xe7` protocol used by lower-end AMT models (1016/2018 NET).

Partition index 0 in the protocol is a read-only AND-aggregate (armed only when all groups are armed) and is intentionally excluded from HA entities. User groups start at protocol index 1.

Full protocol documentation in [`docs/PROTOCOL.md`](docs/PROTOCOL.md).

## Support this project

If this integration saved you time or money, consider supporting its development:

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-fdaneluzzi-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/fdaneluzzi)
[![GitHub Sponsors](https://img.shields.io/badge/GitHub%20Sponsors-fdaneluzzi-EA4AAA?style=for-the-badge&logo=githubsponsors&logoColor=white)](https://github.com/sponsors/fdaneluzzi)

<details>
<summary>PIX (Brasil)</summary>

Chave aleatória: `aae9a1b1-11e2-4282-a16d-7df8f48ae903`

</details>

## License

MIT

[hacs-shield]: https://img.shields.io/badge/HACS-Custom-orange.svg
[hacs-url]: https://hacs.xyz
[release-shield]: https://img.shields.io/github/release/fdaneluzzi/homeassistant-amt8000.svg
[release-url]: https://github.com/fdaneluzzi/homeassistant-amt8000/releases
