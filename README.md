# Home Assistant integration for Solar Manager (v3, read-only)

A **read-only** Home Assistant integration for [Solar Manager](https://www.solar-manager.ch/). Supports two transports — pick at setup or switch later:

- **Cloud** — talks to `https://cloud.solar-manager.ch` with your Solar Manager account.
- **Local** — talks directly to the gateway on your LAN over HTTPS with an API key, no cloud dependency.

It exposes the household-level (gateway) live W values plus per-device sensors. In cloud mode the gateway's own monotonic Wh counters (`iWhTotal` / `eWhTotal`) feed the **Energy dashboard** directly — no Riemann helpers required.

> **Read-only by design.** No `PUT` endpoints are called. No battery-mode or heat-pump-mode control surface is exposed. Write capability, if added, is deferred to v1.0 and would land behind an explicit option (see `CONTRIBUTING.md`).

## Installation

### Via HACS (recommended)

1. HACS → ⋮ → Custom repositories.
2. Repository URL: `https://github.com/ettoreferranti/ha_solarmanager`, Type: Integration → Add.
3. Search "Solar Manager (v3, read-only)" → Download → restart Home Assistant.
4. Settings → Devices & Services → **+ Add Integration** → "Solar Manager (v3, read-only)".
5. Pick **Cloud** or **Local** in the menu step (see below for what each needs).

### Manual

Copy `custom_components/solarmanager_v3/` into your HA config's `custom_components/` directory, restart, then proceed from step 4 above.

## Choosing a transport

### Cloud mode

Needs:
- Your Solar Manager account e-mail and password.
- Your gateway `smId` (16-character ID printed on the back of the gateway, or visible in the URL when logged into the Solar Manager web app).

Best for: full feature parity. All gateway and per-device sensors below are available.

### Local mode

Needs:
- Your gateway's local IP or hostname (e.g. `192.168.1.133`).
- An API key generated from the gateway's web UI (Settings → API access → enable, then add a key — you enter a password, the UI hashes and stores it; the password you typed is what HA needs).
- *Optional:* your `smId` — used only as the entity-ID prefix. Supply the same value you had in cloud mode and your entity history is preserved when migrating.

Best for: lower latency, works without internet, no cloud rate limits.

### Switching transports later

Settings → Devices & Services → Solar Manager → ⋮ → **Configure**. Pick the other transport, fill in its credentials, save. The entry reloads with the new transport; entity unique IDs are preserved if `smId` matches.

## What you get

### Gateway-level sensors (under "Solar Manager Gateway (smId)")

| Entity | Field | Unit | Cloud | Local |
|---|---|---|:---:|:---:|
| PV Production Power | `pW` | W | ✓ | ✓ |
| Household Consumption Power | `cW` | W | ✓ | ✓ |
| Grid Import Power | `iW` | W | ✓ | ✓\* |
| Grid Export Power | `eW` | W | ✓ | ✓\* |
| Battery Charge Power | `bcW` | W | ✓ | ✓ |
| Battery Discharge Power | `bdW` | W | ✓ | ✓ |
| Battery State of Charge | `soc` | % | ✓ | ✓ |

\* In local mode, `iW` and `eW` are synthesized from the grid meter device's signed `power` field (the local API doesn't expose them as gateway fields directly).

### Per-device sensors (one device per Solar Manager-registered inverter / battery / meter)

`power`, `soc`, `temperature`, `activeDevice`, `signal` — available in both transports for any device whose payload includes the field.

**Cumulative per-device energy** (`iWhTotal` "Energy Consumed", `eWhTotal` "Energy Produced") — **cloud only.** The local API's per-device `iWh`/`eWh` fields exist but are not strictly monotonic, so they aren't mapped to `total_increasing` sensors that the recorder would reject.

Device names and types come from the cloud `/v1/info/sensors` endpoint and are therefore only friendly in cloud mode; in pure local mode (no prior cloud setup) devices appear as `Device <id-suffix>`.

## Wiring up the Energy dashboard

**Cloud mode:** point each Energy dashboard slot directly at the relevant per-device `Energy Consumed` / `Energy Produced` sensor.

- **Solar panels** → inverter device's `Energy Produced`
- **Grid consumption** → grid-meter device's `Energy Consumed`
- **Return to grid** → grid-meter device's `Energy Produced`
- **Home battery storage → Energy going in to the battery** → battery device's `Energy Consumed`
- **Home battery storage → Energy coming out of the battery** → battery device's `Energy Produced`
- **Individual devices** (heat pump, EV, plugs) → that device's `Energy Consumed`

For natively-monitored devices (Easee EV charger, Luxtronik heat pump, etc.) the device's own kWh sensor is usually more accurate than the Solar Manager-reported counter — prefer the native one when available.

**Local mode:** per-device cumulative kWh aren't exposed (see above). Build them yourself with HA's built-in Riemann `integration` helper over the per-device `power` sensors, or rely on per-device native integrations where available.

The gateway-level **W** sensors are available in both transports and feed live-power Lovelace cards (gauges, tile cards, ApexCharts) regardless of mode.

## API endpoints used

### Cloud transport
- `POST /v1/oauth/login` — initial token issue
- `POST /v1/oauth/refresh` — token refresh
- `GET /v1/info/sensors/{smId}` — device list (called once at startup, for naming)
- `GET /v3/users/{smId}/data/stream` — live data (polled every 30 s)

### Local transport
- `GET /v2/point` on the gateway over HTTPS — live data (polled every 30 s). Authenticated with header `X-API-Key: <password>`. TLS uses the gateway's self-signed certificate; verification is off by default and can be toggled in the config form.

## Known limitations

- Polling rate is fixed at 30 s. Will be made user-configurable in a future release.
- Per-device sensors only show fields present in the first stream payload; rare fields appearing later require an HA restart to surface.
- Local mode has no equivalent of the cloud's `/info/sensors` endpoint, so devices have no friendly names (unless `smId` matches a previous cloud setup whose names were already in the entity registry).
- Local mode per-device cumulative kWh sensors are not provided (the API's per-device `iWh`/`eWh` aren't strictly monotonic).
- No translation beyond English and German yet.

## Why a separate integration?

The existing community integration ([Soardiac/ha-solarmanager](https://github.com/Soardiac/ha-solarmanager)) does an excellent job for per-device data and battery-eco controls. It does not expose the v3 stream's gateway aggregates (`pW`/`cW`/`iW`/`eW`/`bcW`/`bdW`/`soc`) as separate sensors, which makes correct Energy dashboard configuration awkward. This integration fills that specific gap, and adds a local-API transport so you can run without the cloud round-trip.

## License

MIT
