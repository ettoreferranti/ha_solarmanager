# Development notes

This document captures design decisions and the reasoning behind them, so future maintainers (human or AI) can pick up the work without losing context.

## What this integration is

A custom Home Assistant integration for [Solar Manager](https://www.solar-manager.ch/), the Swiss home-energy management product. Two interchangeable transports:

- **Cloud** — talks to Solar Manager's published v3 REST API at `cloud.solar-manager.ch` with email/password + JWT.
- **Local** — talks directly to the gateway over HTTPS at `/v2/point` with a static `X-API-Key` header.

The user picks one at setup and can switch later via the options flow. The coordinator and sensor platform are transport-agnostic; both transports return a normalised snapshot dict.

Currently **read-only by design**. Exposes both the gateway-level live aggregates (PV / consumption / grid / battery) and a per-device sensor set, organised cleanly under one config entry.

## Why this exists

The well-known community integration [Soardiac/ha-solarmanager](https://github.com/Soardiac/ha-solarmanager) covers per-device data and exposes battery-eco controls, but does not surface the v3 stream endpoint's gateway-level aggregates (`pW`, `cW`, `iW`, `eW`, `bcW`, `bdW`, `soc`) as separate sensors. Without those, configuring HA's Energy dashboard correctly becomes guesswork. The "Interval" sensors Soardiac exposes are derived counters that don't reliably preserve the daily reset semantics HA's statistics engine expects.

This integration fills that specific gap by reading the canonical gateway aggregates directly from `/v3/users/{smId}/data/stream` and presenting them with proper `device_class` and `state_class` so HA-native helpers (Riemann integral, Utility Meter, Energy dashboard) work correctly on top.

## Architectural decisions

### Read-only

No `PUT` calls anywhere in the codebase. The Solar Manager API supports control endpoints (battery mode, eco limits, heat-pump signals), but we deliberately do not expose them in v0.x.

The reasoning is reversibility: a misconfigured integration can read incorrect numbers, but it cannot accidentally turn off the heating, drain the battery, or rewrite tariff schedules. For a personal-use integration installed by trial-and-error, this is the right default.

If write functionality is added in v0.2+, it must be:
- Behind an explicit options-flow toggle (default off).
- Implemented as HA `service` calls, not as `switch` or `number` entities — so writes only happen via deliberate `service.call`, never as a side-effect of UI fiddling or accidental automation triggers.
- Documented per-service in the README with an explicit risk note.

### Endpoint choice — cloud: v3 stream, not v1 statistics

The v1 `/statistics/gateways/{smId}` endpoint returns daily/monthly/yearly totals — convenient but coarse, and updates only when Solar Manager's backend recomputes (~hourly).

The v3 stream endpoint returns instantaneous power values plus interval Wh, sampled at ~10 s on the gateway and exposed to API consumers on demand. Polling it at 30 s gives near-live data, and HA's own helpers turn the W values into accurate cumulative kWh.

Trade-off: 30 s polling means power spikes shorter than 30 s are missed. Acceptable for heat pumps, PV arrays, and batteries — these don't change in sub-30 s bursts that materially affect daily energy. Less accurate for high-frequency loads like microwaves, but plug-level monitoring is best done with Shelly devices or similar, not via the Solar Manager aggregator.

### Endpoint choice — local: /v2/point

Reverse-engineered from a working gateway. Single endpoint returning a snapshot dict that overlaps significantly with the cloud `/stream` payload but is leaner:

- No `iW`/`eW` at the gateway level — we synthesize them from the grid meter device's signed `power`. The grid meter is identified at runtime as the device whose cumulative `iWh`/`eWh` is closest to the gateway-level totals; the `_id` is cached for the LocalTransport instance after first identification, so transient near-zero polls don't lose the entities.
- No `/info/sensors` equivalent — device naming is unavailable in pure local mode.
- Per-device `iWh`/`eWh` are exposed but observation shows they are **not** strictly monotonic. They are deliberately NOT mapped to `iWhTotal`/`eWhTotal` (the cloud's cumulative counters), to avoid feeding non-monotonic values into `total_increasing` sensors that the recorder would warn about.

Auth: the gateway UI accepts a plaintext password, hashes it with SHA-512, and stores the hash. The HTTP API expects the **plaintext** password in the `X-API-Key` header — the server re-hashes incoming requests and compares.

TLS: the gateway uses a self-signed certificate; `verify_ssl` defaults to `False` in `LocalTransport`. Users can opt in via the config form if they've installed the gateway's CA on HA.

### kWh derivation lives in HA config, not the integration

The integration deliberately does **not** expose Riemann-integrated cumulative kWh sensors. Instead, the README instructs users to create them via HA's built-in `integration` platform with `method: trapezoidal`.

Reasoning:
- HA's Riemann helpers are well-tested, version-controlled, and survive integration updates.
- Putting the math in HA config keeps the integration small, focused, and free of state-management concerns (cumulative counters need careful handling on restart, midnight, sensor unavailability, etc. — all problems HA already solved).
- Users who don't want kWh tracking don't get sensors they didn't ask for.
- Per-device kWh from `iWhTotal`/`eWhTotal` (proper monotonic counters from the API) is on the roadmap and would be exposed as `total_increasing` directly — that's API-native data and belongs in the integration. The W → kWh derivation does not.

### Per-device sensors are payload-driven

In `sensor.py`, per-device entities are created only for fields actually present in the first stream payload poll. A solar inverter without a battery doesn't get a SOC entity; a plug without a temperature sensor doesn't get one either.

Trade-off: if Solar Manager later adds a new field to a device's payload, surfacing it requires an HA restart. Acceptable; the alternative (always create every potential entity, marked unavailable for missing fields) clutters the UI and confuses users.

### Token management: 401-retry-once

The Solar Manager API documentation does not specify access-token TTL. We default to 3600 s but treat any HTTP 401 as "refresh and retry once". Refresh failures fall back to full re-login.

This means the integration self-heals from token expiry without needing accurate TTL knowledge. The cost is one extra round-trip per token-expiry event, which happens every hour at most.

### One config entry per gateway

Each Solar Manager gateway (smId) is one config entry. Users with multiple sites can add the integration multiple times. The `unique_id` set in the config flow prevents duplicate entries for the same gateway.

## File layout

```
custom_components/solarmanager_v3/
├── __init__.py          # async_setup_entry, async_unload_entry, transport builder
├── transport.py         # SolarManagerTransport protocol + CloudTransport + LocalTransport
├── config_flow.py       # Cloud/Local menu + per-transport forms + options flow
├── const.py             # endpoint URLs, polling interval, sensor field maps, transport keys
├── coordinator.py       # SolarManagerCoordinator: transport-agnostic polling
├── sensor.py            # Gateway and per-device sensor entities (filter by key presence)
├── manifest.json
├── strings.json         # Config flow text (master)
└── translations/
    ├── en.json
    └── de.json
```

## Domain naming

Domain is `solarmanager_v3`, *not* `solarmanager`, to coexist with the Soardiac integration if a user has both installed (e.g. during migration). Picking a unique domain from day one avoids HA-level conflicts and HACS validation rejections.

## API observations

### Cloud
- The login response field names are not strictly documented — code accepts both `accessToken`/`access_token` styles to survive backend renames.
- `GET /v1/info/sensors/{smId}` returns a list, not an object. Each item has `_id`, `name`, `type`, etc. We use this for friendly device naming on first setup.
- The `devices[]` array in the stream response includes one entry per registered Solar Manager device. Field availability per device varies — see `_id`-based device matching in `sensor.py`.
- Stream polling at < 10 s makes no sense; the gateway internally aggregates over 10 s windows and returns the same snapshot. 30 s is a good default; 60 s reasonable for low-traffic accounts.

### Local
- `/v2/point` returns the same general shape as the cloud `/stream` (top-level snapshot + `devices[]`) but slimmer. See `LocalTransport._normalize` for the field-by-field mapping.
- The gateway-level cumulative energies (`pWh`, `cWh`, `iWh`, `eWh`, etc.) are NOT strictly monotonic across the day — observation shows them resetting/dropping in the evening. They are not exposed as `total_increasing` sensors.
- Per-device `iWh`/`eWh` have similar non-monotonic behaviour (small downward ticks of 0.01–0.02 Wh between polls). The v0.3.2 release removed the alias that fed them into `iWhTotal`/`eWhTotal` sensors.

## Testing approach (not yet implemented)

The integration has no automated tests yet. When adding them:
- `pytest` + `pytest-homeassistant-custom-component` is the conventional choice.
- `aioresponses` for mocking HTTP calls in `transport.py`.
- Test coverage priorities:
  - `CloudTransport`: token refresh logic, 401 retry-once, malformed responses.
  - `LocalTransport._identify_grid_meter`: real payload fixtures covering day-time (large eWh), night-time (tiny eWh near zero), all-zero (post-boot), ambiguous (multiple devices tied).
  - Sensor entity value extraction with edge cases (None, missing field, wrong type).
  - Config flow: both Cloud and Local paths, invalid creds, network error, duplicate gateway.

## How we got here (summary)

1. The existing community integration (Soardiac) gave inaccurate numbers in HA's Energy dashboard.
2. Investigation of the Solar Manager v3 API revealed gateway-level aggregate fields the community integration didn't expose.
3. Rather than fork and patch upstream, we wrote a minimal new integration focused on the gateway-aggregate gap → v0.1.0.
4. v0.2.0 added per-device cumulative kWh sensors (`iWhTotal` / `eWhTotal`) so the Energy dashboard could be wired without Riemann helpers.
5. v0.3.x added the local API transport. The `/v2/point` endpoint was discovered by capturing the request the gateway's web UI makes, mapping responses to the existing snapshot shape, and synthesising the missing `iW`/`eW` grid-power fields from the grid meter's signed `power` (the meter is the device whose cumulative `iWh`/`eWh` matches the gateway totals).
6. v0.3.0 itself shipped broken on HA 2026.x — `async_timeout` was no longer bundled, and `OptionsFlow.__init__` had been removed in HA 2025.12. v0.3.1 fixed both. v0.3.2 fixed the per-device energy aliasing that was producing recorder warnings.
