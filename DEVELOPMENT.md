# Development notes

This document captures design decisions and the reasoning behind them, so future maintainers (human or AI) can pick up the work without losing context.

## What this integration is

A custom Home Assistant integration for [Solar Manager](https://www.solar-manager.ch/), the Swiss home-energy management product, built directly against their published v3 cloud API.

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

### Endpoint choice: v3 stream, not v1 statistics

The v1 `/statistics/gateways/{smId}` endpoint returns daily/monthly/yearly totals — convenient but coarse, and updates only when Solar Manager's backend recomputes (~hourly).

The v3 stream endpoint returns instantaneous power values plus interval Wh, sampled at ~10 s on the gateway and exposed to API consumers on demand. Polling it at 30 s gives near-live data, and HA's own helpers turn the W values into accurate cumulative kWh.

Trade-off: 30 s polling means power spikes shorter than 30 s are missed. Acceptable for heat pumps, PV arrays, and batteries — these don't change in sub-30 s bursts that materially affect daily energy. Less accurate for high-frequency loads like microwaves, but plug-level monitoring is best done with Shelly devices or similar, not via the Solar Manager aggregator.

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
├── __init__.py          # async_setup_entry, async_unload_entry
├── api.py               # SolarManagerClient: aiohttp-based, login + refresh + GET
├── config_flow.py       # UI wizard for email/password/smId
├── const.py             # endpoint URLs, polling interval, sensor field maps
├── coordinator.py       # SolarManagerCoordinator: 30 s polling DataUpdateCoordinator
├── sensor.py            # Gateway and per-device sensor entities
├── manifest.json
├── strings.json         # Config flow text (master)
└── translations/
    ├── en.json
    └── de.json
```

## Domain naming

Domain is `solarmanager_v3`, *not* `solarmanager`, to coexist with the Soardiac integration if a user has both installed (e.g. during migration). Picking a unique domain from day one avoids HA-level conflicts and HACS validation rejections.

## API observations

- The login response field names are not strictly documented — code accepts both `accessToken`/`access_token` styles to survive backend renames.
- `GET /v1/info/sensors/{smId}` returns a list, not an object. Each item has `_id`, `name`, `type`, etc. We use this for friendly device naming on first setup.
- The `devices[]` array in the stream response includes one entry per registered Solar Manager device. Field availability per device varies — see `_id`-based device matching in `sensor.py`.
- Stream polling at < 10 s makes no sense; the gateway internally aggregates over 10 s windows and returns the same snapshot. 30 s is a good default; 60 s reasonable for low-traffic accounts.

## Testing approach (not yet implemented)

The integration has no automated tests yet. When adding them:
- `pytest` + `pytest-homeassistant-custom-component` is the conventional choice.
- `aioresponses` for mocking HTTP calls in `api.py`.
- Test coverage priorities: token refresh logic in `api.py`, payload field extraction in `sensor.py`, config flow validation in `config_flow.py`.

## How we got here (summary)

This integration was developed in a single session where:
1. The user reported the existing community integration (Soardiac) gave inaccurate numbers in HA's Energy dashboard.
2. Investigation of the Solar Manager v3 API revealed gateway-level aggregate fields the community integration didn't expose.
3. Rather than fork and patch upstream, we wrote a minimal new integration focused on the gateway-aggregate gap.
4. The integration was published to GitHub and installed via HACS as a custom repository, then a v0.1.0 release.
5. A separate `configuration.yaml` block creates 10 Riemann integral helpers on top of the integration's W sensors, providing the kWh counters the Energy dashboard requires.
6. Heat-pump and EV-charger kWh come from native integrations (Luxtronik for heat pump, Easee for EV) which provide device-measured kWh — more accurate than Riemann-derived from polled W.
