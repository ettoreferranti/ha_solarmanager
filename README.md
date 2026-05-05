# Home Assistant integration for Solar Manager (v3, read-only)

A minimal, **read-only** Home Assistant integration for [Solar Manager](https://www.solar-manager.ch/), built on the official v3 cloud API.

It exposes the household-level (gateway) live W values plus per-device sensors, including the gateway's own monotonic Wh counters (`iWhTotal` / `eWhTotal`) which feed the **Energy dashboard** directly — no Riemann helpers required.

> **Read-only by design.** This integration intentionally does not call any `PUT` endpoints. No battery-mode or heat-pump-mode control surface is exposed. If those are ever added, they will land behind an explicit option in a future v0.2.

## Installation

### Via HACS (recommended)

1. HACS → ⋮ → Custom repositories.
2. Repository URL: `https://github.com/ettoreferranti/ha_solarmanager`, Type: Integration → Add.
3. Search "Solar Manager (v3, read-only)" → Download → restart Home Assistant.
4. Settings → Devices & Services → **+ Add Integration** → "Solar Manager (v3, read-only)".
5. Enter your Solar Manager cloud e-mail, password, and your `smId` (16-character gateway ID — printed on the back of your Solar Manager device, or visible in the URL when logged into the Solar Manager web app).

### Manual

Copy `custom_components/solarmanager/` into your HA config's `custom_components/` directory, restart, then proceed from step 4 above.

## What you get

### Gateway-level sensors (under "Solar Manager Gateway (smId)")

| Entity | Field | Unit |
|---|---|---|
| PV Production Power | `pW` | W |
| Household Consumption Power | `cW` | W |
| Grid Import Power | `iW` | W |
| Grid Export Power | `eW` | W |
| Battery Charge Power | `bcW` | W |
| Battery Discharge Power | `bdW` | W |
| Battery State of Charge | `soc` | % |

### Per-device sensors (one device per Solar Manager-registered inverter / battery / meter)

`power`, `soc`, `temperature`, `activeDevice`, `signal`, `iWhTotal` (Energy Consumed, Wh), `eWhTotal` (Energy Produced, Wh) — only the fields actually present in the stream payload for that device.

`iWhTotal` / `eWhTotal` are exposed with `device_class: energy` and `state_class: total_increasing` — native Wh from the gateway, displayed by HA in kWh.

## Wiring up the Energy dashboard

Point each Energy dashboard slot directly at the relevant per-device `Energy Consumed` / `Energy Produced` sensor. These map to the gateway's own measured Wh accumulators, so totals match what Solar Manager's web UI shows. No Riemann helpers required.

Settings → Dashboards → Energy → for each slot:

- **Solar panels** → inverter device's `Energy Produced`
- **Grid consumption** → grid-meter device's `Energy Consumed`
- **Return to grid** → grid-meter device's `Energy Produced`
- **Home battery storage → Energy going in to the battery** → battery device's `Energy Consumed`
- **Home battery storage → Energy coming out of the battery** → battery device's `Energy Produced`
- **Individual devices** (heat pump, EV, plugs) → that device's `Energy Consumed`

For natively-monitored devices (Easee EV charger, Luxtronik heat pump, etc.) the device's own kWh sensor is usually more accurate than the Solar Manager-reported counter — prefer the native one when available.

The gateway-level **W** sensors (`pW`/`cW`/`iW`/`eW`/`bcW`/`bdW`) remain available for live-power Lovelace cards (gauges, tile cards, ApexCharts) but are no longer the recommended path for Energy dashboard sources.

## API endpoints used

- `POST /v1/oauth/login` — initial token issue
- `POST /v1/oauth/refresh` — token refresh
- `GET /v1/info/sensors/{smId}` — device list (called once at startup, for naming)
- `GET /v3/users/{smId}/data/stream` — live data (polled every 30 s)

Polling rate is fixed at 30 s in v0.1; configurable in a future release.

## Known limitations

- Polling rate not yet user-configurable.
- Per-device sensors only show fields present in the first stream payload; rare fields appearing later require a HA restart to surface.
- No translation beyond English and German yet.

## Why a separate integration?

The existing community integration ([Soardiac/ha-solarmanager](https://github.com/Soardiac/ha-solarmanager)) does an excellent job for per-device data and battery-eco controls. It does not expose the v3 stream's gateway aggregates (`pW`/`cW`/`iW`/`eW`/`bcW`/`bdW`/`soc`) as separate sensors, which makes correct Energy dashboard configuration awkward. This integration fills that specific gap.

## License

MIT
