# TODO

Concrete next steps, prioritised. Pick one and start a Claude Code session asking "implement TODO #N".

## v0.2 — close the gap with the existing community integration

### 1. Per-device cumulative kWh sensors (high value, easy)

The v3 stream payload includes per-device `iWhTotal` and `eWhTotal` fields — proper monotonic counters that reset at midnight or roll over by accumulation, depending on device type. Surface these as `state_class: total_increasing` sensors so users don't need Riemann helpers for per-device kWh.

Files: `const.py` (extend `DEVICE_SENSORS`), `sensor.py` (special-case the device-class for these — they're `energy`, not `power`).

Acceptance: after install, every device with a non-null `iWhTotal` field exposes a `*_lifetime_consumed` sensor in kWh. Same for `eWhTotal` → `*_lifetime_produced` for inverters.

### 2. Configurable polling interval

Currently hardcoded to 30 s in `const.py`. Move into an options flow so users can pick 10 / 30 / 60 / 300 s without editing code.

Files: `config_flow.py` (add `OptionsFlow`), `coordinator.py` (read from `entry.options`).

Acceptance: Settings → Devices & Services → Solar Manager → Configure → polling interval slider. Change applies on next coordinator tick.

### 3. Sensible defaults for newly-discovered devices

Currently per-device sensors are payload-driven (only fields present in first poll get entities). If a user adds a device to Solar Manager mid-life, an HA restart is required.

Improvement: detect new devices on every poll, register them dynamically. HA supports this via `async_add_entities` from the coordinator listener.

Files: `sensor.py` (entity registration), `__init__.py` (wire up the dynamic listener).

Acceptance: add a new plug in Solar Manager → it appears in HA within one polling cycle.

## v0.3 — quality

### 4. Unit tests

Zero coverage today. Bring it up to at least:
- API client: token refresh, 401-retry, malformed responses
- Config flow: valid creds, invalid creds, network error, duplicate gateway
- Sensor entity value extraction with edge cases (None, missing field, wrong type)

Tooling: `pytest` + `pytest-homeassistant-custom-component` + `aioresponses`.

### 5. Brand assets

Submit logo + icon to <https://github.com/home-assistant/brands> so the integration shows the Solar Manager logo in HA's UI instead of the generic placeholder. Asset requirements documented in that repo.

### 6. Translations

Currently EN and DE only. Italian and French would be appreciated by Swiss users.

## v1.0 — write capability (deliberately deferred)

Only after v0.x line is stable and well-tested. See CONTRIBUTING.md "Read-only guarantee" section for the rules.

Candidate writeable services, from highest to lowest priority by likely user value:

- `solarmanager_v3.set_battery_eco_limit` — daily reserve % the battery should keep
- `solarmanager_v3.set_battery_charge_target` — force-charge to N% by time T
- `solarmanager_v3.set_device_priority` — reorder load priority for the dispatcher

All require careful UX so users don't fire them by accident. Each must have:
- Confirmation dialog in the service call
- Bounded input validation (no -1% battery, no 200% targets)
- Clear logging of every write

## Maintenance hygiene

- Tag a release after every functionally meaningful merge to `main`.
- Watch <https://github.com/home-assistant/core> deprecation announcements for HA framework changes affecting custom integrations.
- The Solar Manager API has versioned itself once (v1 → v3). If a v4 appears, evaluate whether to migrate or maintain both.

## Long-term, "if interested" ideas

- Expose a service that returns the raw stream payload as an attribute — useful for users wanting to template novel calculations.
- Add Forecast.Solar integration: combine your latitude/longitude/panel-orientation with HA's built-in forecast to show "expected vs actual" PV bars.
- Energy-cost integration: pull EKZ tariff schedule from a Swiss tariff API (if one exists) and overlay cost on the energy dashboard.
- Companion Lovelace card: a polished single-card view showing live distribution + daily totals + top consumers, designed for the living-room screen kiosk.
